from __future__ import annotations

import io
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple, List

import requests
try:
    from googleapiclient.discovery import build  # type: ignore
    from googleapiclient.errors import HttpError  # type: ignore
    from googleapiclient.http import MediaIoBaseUpload  # type: ignore
    from google.oauth2.credentials import Credentials  # type: ignore
    from google.auth.transport.requests import Request  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    build = None  # type: ignore[assignment]
    HttpError = Exception  # type: ignore[assignment]
    MediaIoBaseUpload = None  # type: ignore[assignment]
    Credentials = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]

from config import config
from database import db
import hashlib
from file_manager import backup_manager
import logging


DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def start_device_authorization(user_id: int) -> Dict[str, Any]:
    """Starts OAuth Device Authorization flow for Google Drive.

    Returns a dict with: verification_url, user_code, device_code, interval, expires_in.
    """
    if not config.GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID is not set")
    payload = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "scope": config.GOOGLE_OAUTH_SCOPES,
    }
    # Some Google OAuth client types (e.g., Web) require client_secret
    if getattr(config, "GOOGLE_CLIENT_SECRET", None):
        payload["client_secret"] = config.GOOGLE_CLIENT_SECRET  # type: ignore[index]
    try:
        response = requests.post(DEVICE_CODE_URL, data=payload, timeout=15)
        # If unauthorized/invalid_client, surface clearer message
        if response.status_code >= 400:
            try:
                err = response.json()
            except Exception:
                err = {"error": f"HTTP {response.status_code}"}
            msg = err.get("error_description") or err.get("error") or f"HTTP {response.status_code}"
            raise RuntimeError(f"Device auth start failed: {msg}")
        data = response.json()
    except requests.RequestException as e:
        raise RuntimeError("Device auth request error") from e
    # Persist device flow state in memory is handled by caller; tokens saved on success.
    return {
        "verification_url": data.get("verification_url") or data.get("verification_uri"),
        "user_code": data.get("user_code"),
        "device_code": data.get("device_code"),
        "interval": int(data.get("interval", 5)),
        "expires_in": int(data.get("expires_in", 1800)),
    }


def poll_device_token(device_code: str) -> Optional[Dict[str, Any]]:
    """Attempts a single token exchange for a device_code.

    Returns:
        - dict with tokens on success
        - None if authorization is still pending or needs to slow down
        - dict with {"error": <code>, "error_description": <str>} on user-facing errors
    """
    payload = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    # Include client_secret if configured to satisfy clients that require it
    if getattr(config, "GOOGLE_CLIENT_SECRET", None):
        payload["client_secret"] = config.GOOGLE_CLIENT_SECRET  # type: ignore[index]
    resp = requests.post(TOKEN_URL, data=payload, timeout=20)
    if resp.status_code >= 400:
        # Try to parse structured OAuth error
        try:
            data = resp.json()
            err = (data or {}).get("error")
            desc = (data or {}).get("error_description")
        except Exception:
            err, desc = None, None
        # Pending/slowdown are not errors for the UI
        if err in {"authorization_pending", "slow_down"}:
            logging.getLogger(__name__).debug("Drive auth pending/slow_down")
            return None
        # Access denied / expired / invalid_grant are user-facing errors
        if err in {"access_denied", "expired_token", "invalid_grant",
                    "invalid_request", "invalid_client"}:
            return {"error": err or "bad_request", "error_description": desc}
        # Unknown 400 – return a generic error record
        logging.getLogger(__name__).warning(
            f"Drive auth error: {err} {desc}"
        )
        return {"error": err or f"http_{resp.status_code}", "error_description": desc or "token endpoint error"}
    # Success
    tokens = resp.json()
    tokens["expiry"] = (_now_utc() + timedelta(seconds=int(tokens.get("expires_in", 3600)))).isoformat()
    return tokens


def save_tokens(user_id: int, tokens: Dict[str, Any]) -> bool:
    """Save OAuth tokens, preserving existing refresh_token if missing.

    Some OAuth exchanges (and refreshes) do not return refresh_token again.
    We merge with existing tokens to avoid wiping the refresh_token.
    """
    existing = _load_tokens(user_id) or {}
    merged: Dict[str, Any] = dict(existing)
    merged.update(tokens or {})
    if not merged.get("refresh_token") and existing.get("refresh_token"):
        merged["refresh_token"] = existing["refresh_token"]
    return db.save_drive_tokens(user_id, merged)


def _load_tokens(user_id: int) -> Optional[Dict[str, Any]]:
    return db.get_drive_tokens(user_id)


def _credentials_from_tokens(tokens: Dict[str, Any]) -> Credentials:
    if Credentials is None:
        raise RuntimeError("Google libraries are not installed")
    return Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri=TOKEN_URL,
        client_id=config.GOOGLE_CLIENT_ID,
        client_secret=config.GOOGLE_CLIENT_SECRET or None,
        scopes=(tokens.get("scope") or config.GOOGLE_OAUTH_SCOPES).split(),
    )


def _ensure_valid_credentials(user_id: int) -> Optional[Credentials]:
    tokens = _load_tokens(user_id)
    if not tokens:
        logging.getLogger(__name__).warning("Drive creds missing for user; need login")
        return None
    try:
        creds = _credentials_from_tokens(tokens)
    except Exception:
        return None
    if creds.expired and creds.refresh_token:
        try:
            if Request is None:
                return None
            creds.refresh(Request())  # type: ignore[misc]
            # Persist updated access token and expiry
            updated = {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_type": "Bearer",
                "scope": " ".join(creds.scopes or []),
                "expires_in": int((creds.expiry - _now_utc()).total_seconds()) if creds.expiry else 3600,
                "expiry": creds.expiry.isoformat() if creds.expiry else (_now_utc() + timedelta(hours=1)).isoformat(),
            }
            save_tokens(user_id, updated)
        except Exception:
            logging.getLogger(__name__).exception("Drive token refresh failed")
            return None
    return creds


def get_drive_service(user_id: int):
    if build is None:
        return None
    creds = _ensure_valid_credentials(user_id)
    if not creds:
        return None
    try:
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _get_file_metadata(service, file_id: str, fields: str = "id, name, trashed, mimeType, parents") -> Optional[Dict[str, Any]]:
    """Return file metadata or None if not found/inaccessible."""
    try:
        return service.files().get(fileId=file_id, fields=fields).execute()
    except Exception:
        return None


def ensure_folder(user_id: int, name: str, parent_id: Optional[str] = None) -> Optional[str]:
    service = get_drive_service(user_id)
    if not service:
        return None
    try:
        safe_name = name.replace("'", "\\'")
        q = "name = '{0}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false".format(safe_name)
        if parent_id:
            safe_parent = str(parent_id).replace("'", "\\'")
            q += f" and '{safe_parent}' in parents"
        results = service.files().list(q=q, fields="files(id, name)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = service.files().create(body=metadata, fields="id").execute()
        return folder.get("id")
    except HttpError:
        return None


def get_or_create_default_folder(user_id: int) -> Optional[str]:
    prefs = db.get_drive_prefs(user_id) or {}
    folder_id = prefs.get("target_folder_id")
    # Validate existing folder id is not trashed/deleted
    try:
        service = get_drive_service(user_id)
    except Exception:
        service = None
    if service and folder_id:
        meta = _get_file_metadata(service, folder_id, fields="id, trashed, mimeType")
        if meta and not bool(meta.get("trashed")) and str(meta.get("mimeType")) == "application/vnd.google-apps.folder":
            return folder_id
        # stale/trashed id — ignore and recreate below
        folder_id = None
    if folder_id:
        # No service to validate — optimistically return; upload will validate again
        return folder_id
    # Create or find non-trashed default root folder at Drive
    fid = ensure_folder(user_id, "גיבויי_קודלי", None)
    if fid:
        db.save_drive_prefs(user_id, {"target_folder_id": fid})
    return fid


def ensure_path(user_id: int, path: str) -> Optional[str]:
    """Ensure nested folders path like "Parent/Sub1/Sub2" exists; returns last folder id."""
    if not path:
        return get_or_create_default_folder(user_id)
    parts = [p.strip() for p in path.split('/') if p.strip()]
    parent: Optional[str] = None
    for part in parts:
        parent = ensure_folder(user_id, part, parent)
        if not parent:
            return None
    # Save as target folder
    db.save_drive_prefs(user_id, {"target_folder_id": parent})
    return parent


def _get_root_folder(user_id: int) -> Optional[str]:
    """Return user's target root folder id, validating it's active; create default if needed."""
    return get_or_create_default_folder(user_id)


def ensure_subpath(user_id: int, sub_path: str) -> Optional[str]:
    """Ensure nested subfolders under the user's root. Does not change prefs."""
    root_id = _get_root_folder(user_id)
    if not root_id:
        return None
    if not sub_path:
        return root_id
    parts = [p.strip() for p in sub_path.split('/') if p.strip()]
    parent = root_id
    for part in parts:
        parent = ensure_folder(user_id, part, parent)
        if not parent:
            return None
    return parent


def _date_path() -> str:
    now = _now_utc()
    return f"{now.year:04d}/{now.month:02d}-{now.day:02d}"


def _date_str_ddmmyyyy() -> str:
    now = _now_utc()
    return f"{now.day:02d}-{now.month:02d}-{now.year:04d}"


def _next_version(user_id: int, key: str) -> int:
    prefs = db.get_drive_prefs(user_id) or {}
    counters = dict(prefs.get("drive_version_counters") or {})
    current = int(counters.get(key, 0) or 0) + 1
    counters[key] = current
    db.save_drive_prefs(user_id, {"drive_version_counters": counters})
    return current


def _category_label(category: str) -> str:
    mapping = {
        # For ZIP we use english label 'zip' for filename consistency
        "zip": "zip",
        "all": "הכל",
        "by_repo": "לפי_ריפו",
        "large": "קבצים_גדולים",
        "other": "שאר_קבצים",
    }
    return mapping.get(category, category)


def compute_subpath(category: str, repo_name: Optional[str] = None) -> str:
    """Return destination subpath under the user's root folder.

    Simplified structure without date-based nesting to avoid deep paths:
    - zip        -> "zip"
    - all        -> "הכל"
    - by_repo    -> "לפי_ריפו/<repo_name>"
    - large      -> "קבצים_גדולים"
    - other      -> "שאר_קבצים"
    """
    base = _category_label(category)
    if category == "by_repo" and repo_name:
        return f"{base}/{repo_name}"
    return base


def _rating_to_emoji(rating: Optional[str]) -> str:
    if not rating:
        return ""
    r = str(rating)
    if "🏆" in r:
        return "🏆"
    if "👍" in r:
        return "👍"
    if "🤷" in r:
        return "🤷"
    return ""


def _short_hash(data: Optional[bytes]) -> str:
    if not data:
        return ""
    try:
        import hashlib
        return hashlib.sha256(data).hexdigest()[:8]
    except Exception:
        return ""


def compute_friendly_name(user_id: int, category: str, entity_name: str, rating: Optional[str] = None, content_sample: Optional[bytes] = None) -> str:
    """Return a friendly filename per spec using underscores.

    Pattern examples:
    - BKP_zip_CodeBot_v7_26-08-2025.zip
    - BKP_zip_CodeBot_v7_🏆_26-08-2025.zip
    """
    label = _category_label(category)
    date_str = _date_str_ddmmyyyy()
    key = f"{category}:{entity_name}"
    v = _next_version(user_id, key)
    emoji = _rating_to_emoji(rating)
    base = f"BKP_{label}_{entity_name}_v{v}"
    # Add short content hash if available to reduce collisions when many zips are generated in a row
    # Hash suffix only if enabled in config
    try:
        from config import config as _cfg
        use_hash = bool(getattr(_cfg, 'DRIVE_ADD_HASH', False))
    except Exception:
        use_hash = False
    h = _short_hash(content_sample) if use_hash else ""
    if emoji and h:
        return f"{base}_{emoji}_{h}_{date_str}.zip"
    if emoji:
        return f"{base}_{emoji}_{date_str}.zip"
    if h:
        return f"{base}_{h}_{date_str}.zip"
    return f"{base}_{date_str}.zip"
def upload_bytes(user_id: int, filename: str, data: bytes, folder_id: Optional[str] = None, sub_path: Optional[str] = None) -> Optional[str]:
    service = get_drive_service(user_id)
    if not service:
        return None
    if sub_path:
        folder_id = ensure_subpath(user_id, sub_path)
    if not folder_id:
        folder_id = _get_root_folder(user_id)
    if not folder_id:
        return None
    if MediaIoBaseUpload is None:
        return None
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/zip", resumable=False)
    body: Dict[str, Any] = {"name": filename}
    if folder_id:
        body["parents"] = [folder_id]
    try:
        file = service.files().create(body=body, media_body=media, fields="id").execute()
        return file.get("id")
    except HttpError:
        return None


def upload_all_saved_zip_backups(user_id: int) -> Tuple[int, List[str]]:
    """Upload only ZIP backups that were not uploaded before for this user.

    Uses db.drive_prefs.uploaded_backup_ids (set) to deduplicate uploads.
    """
    backups = backup_manager.list_backups(user_id)
    uploaded = 0
    ids: List[str] = []
    # Load previously uploaded backup ids
    try:
        prefs = db.get_drive_prefs(user_id) or {}
        uploaded_set = set(prefs.get('uploaded_backup_ids') or [])
    except Exception:
        prefs = {}
        uploaded_set = set()
    # Resolve/validate root; if it changed, drop uploaded_set to allow re‑upload
    old_root_id = prefs.get('target_folder_id')
    try:
        current_root_id = _get_root_folder(user_id)
    except Exception:
        current_root_id = old_root_id
    if current_root_id and old_root_id and current_root_id != old_root_id:
        uploaded_set = set()
        try:
            db.save_drive_prefs(user_id, {"uploaded_backup_ids": []})
        except Exception:
            pass
    # Also deduplicate by content hash against existing files in Drive (folder: zip)
    existing_md5: Optional[set[str]] = set()
    try:
        service = get_drive_service(user_id)
        if service is not None:
            sub_path = compute_subpath("zip")
            folder_id = ensure_subpath(user_id, sub_path)
            if folder_id:
                page_token: Optional[str] = None
                while True:
                    try:
                        resp = service.files().list(
                            q=f"'{folder_id}' in parents and trashed = false",
                            spaces='drive',
                            fields="nextPageToken, files(id, name, md5Checksum)",
                            pageToken=page_token
                        ).execute()
                    except Exception:
                        existing_md5 = None
                        break
                    for f in (resp.get('files') or []):
                        md5v = f.get('md5Checksum')
                        if isinstance(md5v, str) and md5v:
                            assert isinstance(existing_md5, set)
                            existing_md5.add(md5v)
                    page_token = resp.get('nextPageToken')
                    if not page_token:
                        break
    except Exception:
        existing_md5 = None
    new_uploaded: List[str] = []
    for b in backups:
        try:
            b_id = getattr(b, 'backup_id', None)
            path = getattr(b, "file_path", None)
            if not path or not str(path).endswith(".zip"):
                continue
            with open(path, "rb") as f:
                data = f.read()
            # If a file with the same content already exists in Drive, mark as uploaded and skip
            try:
                md5_local = hashlib.md5(data).hexdigest()
                if isinstance(existing_md5, set) and md5_local in existing_md5:
                    if b_id:
                        new_uploaded.append(b_id)
                    continue
                # If we could not list Drive files (existing_md5 is None), fallback to uploaded_set guard
                if existing_md5 is None and b_id and b_id in uploaded_set:
                    continue
            except Exception:
                pass
            from config import config as _cfg
            # Build entity name
            try:
                md = getattr(b, 'metadata', None) or {}
            except Exception:
                md = {}
            repo_full = None
            try:
                repo_full = md.get('repo')
            except Exception:
                repo_full = None
            if not repo_full:
                try:
                    repo_full = getattr(b, 'repo', None)
                except Exception:
                    repo_full = None
            if isinstance(repo_full, str) and repo_full:
                base_name = repo_full.split('/')[-1]
                path_hint = ''
                try:
                    path_hint = (md.get('path') or '').strip('/')
                except Exception:
                    path_hint = ''
                if not path_hint:
                    try:
                        path_hint = (getattr(b, 'path', None) or '').strip('/')
                    except Exception:
                        path_hint = ''
                entity = f"{base_name}_{path_hint.replace('/', '_')}" if path_hint else base_name
            else:
                entity = getattr(_cfg, 'BOT_LABEL', 'CodeBot') or 'CodeBot'
            # Derive rating emoji
            try:
                rating = db.get_backup_rating(user_id, b_id) if b_id else None
            except Exception:
                rating = None
            fname = compute_friendly_name(user_id, "zip", entity, rating, content_sample=data[:1024])
            sub_path = compute_subpath("zip")
            fid = upload_bytes(user_id, filename=fname, data=data, sub_path=sub_path)
            if fid:
                uploaded += 1
                ids.append(fid)
                if b_id:
                    new_uploaded.append(b_id)
        except Exception:
            continue
    # Persist uploaded ids and last backup time for next-run calc
    if new_uploaded:
        try:
            all_ids = list(uploaded_set.union(new_uploaded))
            now_iso = _now_utc().isoformat()
            db.save_drive_prefs(user_id, {"uploaded_backup_ids": all_ids, "last_backup_at": now_iso})
        except Exception:
            pass
    return uploaded, ids


def create_repo_grouped_zip_bytes(user_id: int) -> List[Tuple[str, str, bytes]]:
    """Return zips grouped by repo: (repo_name, suggested_name, zip_bytes)."""
    from database import db as _db
    import zipfile
    files = _db.get_user_files(user_id, limit=10000) or []
    repo_to_files: Dict[str, List[Dict[str, Any]]] = {}
    for doc in files:
        tags = doc.get('tags') or []
        repo_tag = None
        for t in tags:
            if isinstance(t, str) and t.startswith('repo:'):
                repo_tag = t.split(':', 1)[1]
                break
        if not repo_tag:
            continue
        repo_to_files.setdefault(repo_tag, []).append(doc)
    results: List[Tuple[str, str, bytes]] = []
    for repo, docs in repo_to_files.items():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for d in docs:
                name = d.get('file_name') or f"file_{d.get('_id')}"
                code = d.get('code') or ''
                zf.writestr(name, code)
        buf.seek(0)
        data_bytes = buf.getvalue()
        friendly = compute_friendly_name(user_id, "by_repo", repo, content_sample=data_bytes[:1024])
        results.append((repo, friendly, data_bytes))
    return results


def create_full_backup_zip_bytes(user_id: int, category: str = "all") -> Tuple[str, bytes]:
    """Creates a ZIP of user data by category and returns (filename, bytes)."""
    # Collect content according to category
    from database import db as _db
    import zipfile

    backup_id = f"backup_{user_id}_{int(time.time())}_{category}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        files = _db.get_user_files(user_id, limit=10000) or []
        if category == "by_repo":
            files = [d for d in files if any((t or '').startswith('repo:') for t in (d.get('tags') or []))]
        elif category == "large":
            large_files, _ = _db.get_user_large_files(user_id, page=1, per_page=10000)
            for lf in large_files:
                name = lf.get('file_name') or f"large_{lf.get('_id')}"
                code = lf.get('code') or ''
                zf.writestr(name, code)
            # Also write metadata for large
            metadata = {
                "backup_id": backup_id,
                "user_id": user_id,
                "created_at": _now_utc().isoformat(),
                "backup_type": "drive_manual_large",
                "file_count": len(large_files),
            }
            zf.writestr('metadata.json', json.dumps(metadata, ensure_ascii=False, indent=2))
            buf.seek(0)
            return f"{backup_id}.zip", buf.getvalue()
        elif category == "other":
            files = [d for d in files if not any((t or '').startswith('repo:') for t in (d.get('tags') or []))]
        # default include files
        for doc in files:
            name = doc.get('file_name') or f"file_{doc.get('_id')}"
            code = doc.get('code') or ''
            zf.writestr(name, code)
        metadata = {
            "backup_id": backup_id,
            "user_id": user_id,
            "created_at": _now_utc().isoformat(),
            "backup_type": f"drive_manual_{category}",
            "file_count": len(files),
        }
        zf.writestr('metadata.json', json.dumps(metadata, ensure_ascii=False, indent=2))
    buf.seek(0)
    return f"{backup_id}.zip", buf.getvalue()


def perform_scheduled_backup(user_id: int) -> bool:
    """Runs a scheduled backup to Drive according to user's selected category.

    Category resolution priority:
    1) drive_prefs.schedule_category (explicit)
    2) drive_prefs.last_selected_category (UI selection)
    3) fallback to "all"

    Updates last_backup_at on any successful scheduled upload.
    Updates last_full_backup_at only if category == "all".
    """
    try:
        prefs = db.get_drive_prefs(user_id) or {}
    except Exception:
        prefs = {}
    category = str(prefs.get("schedule_category") or prefs.get("last_selected_category") or "all").strip() or "all"
    allowed = {"zip", "all", "by_repo", "large", "other"}
    if category not in allowed:
        category = "all"

    ok = False
    try:
        now_iso = _now_utc().isoformat()
        if category == "zip":
            # Upload any saved ZIP backups that were not uploaded yet
            count, _ids = upload_all_saved_zip_backups(user_id)
            ok = bool(count and count > 0)
            if ok:
                try:
                    db.save_drive_prefs(user_id, {"last_backup_at": now_iso})
                except Exception:
                    pass
        elif category == "by_repo":
            grouped = create_repo_grouped_zip_bytes(user_id)
            ok_any = False
            for repo_name, suggested, data_bytes in grouped:
                # Use suggested friendly name and by_repo subpath
                sub_path = compute_subpath("by_repo", repo_name)
                fid = upload_bytes(user_id, suggested, data_bytes, sub_path=sub_path)
                ok_any = ok_any or bool(fid)
            ok = ok_any
            if ok:
                try:
                    db.save_drive_prefs(user_id, {"last_backup_at": now_iso})
                except Exception:
                    pass
        else:
            # all / large / other -> single ZIP according to category
            fn, data = create_full_backup_zip_bytes(user_id, category=category)
            from config import config as _cfg
            friendly = compute_friendly_name(user_id, category, getattr(_cfg, 'BOT_LABEL', 'CodeBot') or 'CodeBot', content_sample=data[:1024])
            sub_path = compute_subpath(category)
            fid = upload_bytes(user_id, friendly, data, sub_path=sub_path)
            ok = bool(fid)
            if ok:
                update = {"last_backup_at": now_iso}
                if category == "all":
                    update["last_full_backup_at"] = now_iso
                try:
                    db.save_drive_prefs(user_id, update)
                except Exception:
                    pass
    except Exception:
        ok = False
    return ok

