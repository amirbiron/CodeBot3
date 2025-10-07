"""
מנוע סקירת קוד מבוסס AI עם תמיכה ב-Ollama, OpenAI ו-Claude.
ממומש בוריאציה מינימלית ובטוחה כדי לא לשבור את הריפו, עם שימוש ב-cache הקיים ובקונפיג.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import partial
from typing import Any, Dict, List, Optional

import aiohttp

from cache_manager import cache as cache_manager
from config import config

logger = logging.getLogger(__name__)


class AIProvider(Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    CLAUDE = "claude"


class ReviewFocus(Enum):
    FULL = "full"
    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BUGS = "bugs"


@dataclass
class ReviewResult:
    security_issues: List[str] = field(default_factory=list)
    bugs: List[str] = field(default_factory=list)
    performance_issues: List[str] = field(default_factory=list)
    code_quality_issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    score: int = 0
    summary: str = ""
    tokens_used: int = 0
    provider: str = ""
    focus: str = ReviewFocus.FULL.value

    def to_dict(self) -> Dict[str, Any]:
        return {
            "security_issues": self.security_issues,
            "bugs": self.bugs,
            "performance_issues": self.performance_issues,
            "code_quality_issues": self.code_quality_issues,
            "suggestions": self.suggestions,
            "score": self.score,
            "summary": self.summary,
            "tokens_used": self.tokens_used,
            "provider": self.provider,
            "focus": self.focus,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReviewResult":
        return cls(**data)


class RateLimiter:
    def __init__(self, max_per_day: int = 10, max_per_hour: int = 3):
        self.max_per_day = max_per_day
        self.max_per_hour = max_per_hour
        self.user_daily_usage: Dict[int, List[datetime]] = {}
        self.user_hourly_usage: Dict[int, List[datetime]] = {}

    async def check_and_increment(self, user_id: int) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        self._cleanup_old(user_id, now)
        if len(self.user_daily_usage.get(user_id, [])) >= self.max_per_day:
            return False, f"הגעת למגבלת הבקשות היומית ({self.max_per_day} סקירות ליום)"
        if len(self.user_hourly_usage.get(user_id, [])) >= self.max_per_hour:
            return False, "יותר מדי בקשות בשעה האחרונה. המתן מעט ונסה שוב"
        self.user_daily_usage.setdefault(user_id, []).append(now)
        self.user_hourly_usage.setdefault(user_id, []).append(now)
        return True, ""

    def _cleanup_old(self, user_id: int, now: datetime) -> None:
        try:
            self.user_daily_usage[user_id] = [
                ts for ts in self.user_daily_usage.get(user_id, []) if (now - ts).total_seconds() < 86400
            ]
        except Exception:
            self.user_daily_usage[user_id] = []
        try:
            self.user_hourly_usage[user_id] = [
                ts for ts in self.user_hourly_usage.get(user_id, []) if (now - ts).total_seconds() < 3600
            ]
        except Exception:
            self.user_hourly_usage[user_id] = []

    def get_remaining_quota(self, user_id: int) -> Dict[str, int]:
        daily = self.max_per_day - len(self.user_daily_usage.get(user_id, []))
        hourly = self.max_per_hour - len(self.user_hourly_usage.get(user_id, []))
        return {"daily": max(0, daily), "hourly": max(0, hourly)}


class AICodeReviewer:
    MAX_CODE_CHARS = 15000
    MAX_CODE_LINES = 500

    def __init__(self):
        self.provider = self._get_provider()
        self.rate_limiter = RateLimiter(
            max_per_day=int(os.getenv("AI_REVIEW_MAX_PER_DAY", str(getattr(config, "AI_REVIEW_MAX_PER_DAY", 10) or 10))),
            max_per_hour=int(os.getenv("AI_REVIEW_MAX_PER_HOUR", str(getattr(config, "AI_REVIEW_MAX_PER_HOUR", 3) or 3))),
        )
        self.openai_client = None
        self.claude_client = None
        if self.provider == AIProvider.OPENAI:
            try:
                import openai  # type: ignore
                self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY") or getattr(config, "OPENAI_API_KEY", None))
            except Exception:
                logger.error("חבילת openai לא זמינה; מעבר ל-Ollama אם אפשר")
                self.provider = AIProvider.OLLAMA
        elif self.provider == AIProvider.CLAUDE:
            try:
                import anthropic  # type: ignore
                self.claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY") or getattr(config, "ANTHROPIC_API_KEY", None))
            except Exception:
                logger.error("חבילת anthropic לא זמינה; מעבר ל-Ollama אם אפשר")
                self.provider = AIProvider.OLLAMA

    def _get_provider(self) -> AIProvider:
        prov = (os.getenv("AI_PROVIDER") or getattr(config, "AI_PROVIDER", "ollama") or "ollama").lower()
        try:
            return AIProvider(prov)
        except Exception:
            return AIProvider.OLLAMA

    async def review_code(self, code: str, filename: str, user_id: int, focus: ReviewFocus = ReviewFocus.FULL) -> ReviewResult:
        allowed, msg = await self.rate_limiter.check_and_increment(user_id)
        if not allowed:
            r = ReviewResult(provider=self.provider.value, focus=focus.value)
            r.summary = f"❌ {msg}"
            return r
        if len(code) > self.MAX_CODE_CHARS or len(code.splitlines()) > self.MAX_CODE_LINES:
            code = self._truncate_code(code)

        cache_key = self._cache_key(code, filename, focus)
        cached = None
        try:
            cached = cache_manager.get(cache_key)
        except Exception:
            cached = None
        if cached:
            try:
                return ReviewResult.from_dict(cached)
            except Exception:
                pass

        try:
            if self.provider == AIProvider.OPENAI:
                result = await self._review_with_openai(code, filename, focus)
            elif self.provider == AIProvider.CLAUDE:
                result = await self._review_with_claude(code, filename, focus)
            else:
                result = await self._review_with_ollama(code, filename, focus)
            result.focus = focus.value
            try:
                cache_manager.set(cache_key, result.to_dict(), expire_seconds=int(os.getenv("AI_REVIEW_CACHE_TTL", "86400")))
            except Exception:
                pass
            return result
        except Exception as e:
            logger.error(f"שגיאה בסקירת קוד: {e}")
            r = ReviewResult(provider=self.provider.value, focus=focus.value)
            r.summary = f"❌ שגיאה בסקירה: {e}"
            return r

    def _cache_key(self, code: str, filename: str, focus: ReviewFocus) -> str:
        content = f"{filename}:{focus.value}:{code}"
        return f"ai_review:{hashlib.sha256(content.encode()).hexdigest()}"

    def _truncate_code(self, code: str) -> str:
        lines = code.splitlines()
        if len(lines) > self.MAX_CODE_LINES:
            keep = self.MAX_CODE_LINES // 2
            return "\n".join(lines[:keep]) + "\n\n... (קוד נוסף הושמט) ...\n\n" + "\n".join(lines[-keep:])
        if len(code) > self.MAX_CODE_CHARS:
            keepc = self.MAX_CODE_CHARS // 2
            return code[:keepc] + "\n\n... (קוד נוסף הושמט) ...\n\n" + code[-keepc:]
        return code

    def _build_prompt(self, code: str, filename: str, focus: ReviewFocus) -> str:
        file_ext = filename.split(".")[-1] if "." in filename else "unknown"
        base = (
            f"אנא בצע סקירת קוד מקצועית עבור הקובץ הבא:\n\n"
            f"שם קובץ: {filename}\nשפה/סוג: {file_ext}\n\n"
            f"הקוד:\n```{file_ext}\n{code}\n```\n"
        )
        if focus == ReviewFocus.SECURITY:
            spec = "התמקד רק בבעיות אבטחה"
        elif focus == ReviewFocus.PERFORMANCE:
            spec = "התמקד רק בבעיות ביצועים"
        elif focus == ReviewFocus.STYLE:
            spec = "התמקד רק בסגנון קוד"
        elif focus == ReviewFocus.BUGS:
            spec = "התמקד רק בבאגים פוטנציאליים"
        else:
            spec = "בצע סקירה מקיפה"
        fmt = (
            '{"security_issues":[],"bugs":[],"performance_issues":[],"code_quality_issues":[],"suggestions":[],"score":5,"summary":""}'
        )
        # דרישה מפורשת לתוכן לא ריק ב-summary כדי למנוע תשובה ריקה
        guidelines = (
            "\n\nהנחיות:\n"
            "1) החזר JSON תקין בלבד.\n"
            "2) summary חייב להכיל 2–4 משפטים.\n"
            "3) אם אין ממצאים, הסבר מדוע והצע שתי הצעות שיפור כלליות.\n"
        )
        return base + "\n" + spec + guidelines + "\nהשב בפורמט JSON בלבד:\n" + fmt

    def _parse_ai_response(self, content: str, provider: str) -> ReviewResult:
        res = ReviewResult(provider=provider)
        try:
            s = content[content.find("{") : content.rfind("}") + 1]
            data = json.loads(s)
            res.security_issues = list(data.get("security_issues", []))
            res.bugs = list(data.get("bugs", []))
            res.performance_issues = list(data.get("performance_issues", []))
            res.code_quality_issues = list(data.get("code_quality_issues", []))
            res.suggestions = list(data.get("suggestions", []))
            try:
                res.score = int(data.get("score", 0))
            except Exception:
                res.score = 0
            res.summary = str(data.get("summary", ""))
            if not (res.summary or "").strip():
                # אם הסיכום ריק – הצג את הטקסט הגולמי שקיבלנו (עד 800 תווים)
                res.summary = (content or "").strip()[:800]
        except Exception:
            res.summary = content[:500]
        return res

    async def _review_with_ollama(self, code: str, filename: str, focus: ReviewFocus) -> ReviewResult:
        url = os.getenv("OLLAMA_URL") or getattr(config, "OLLAMA_URL", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL") or getattr(config, "OLLAMA_MODEL", "deepseek-coder:6.7b")
        prompt = self._build_prompt(code, filename, focus)
        payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.3, "num_predict": 1000}}
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{url}/api/generate", json=payload, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Ollama שגיאה: {resp.status}")
                data = await resp.json()
                content = data.get("response", "")
        return self._parse_ai_response(content, AIProvider.OLLAMA.value)

    async def _review_with_openai(self, code: str, filename: str, focus: ReviewFocus) -> ReviewResult:
        if not self.openai_client:
            raise RuntimeError("OpenAI client לא זמין")
        prompt = self._build_prompt(code, filename, focus)
        loop = asyncio.get_event_loop()
        model = (os.getenv("OPENAI_MODEL") or getattr(config, "OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
        # נסה קודם את Responses API עבור מודלים מסדרת GPT-5 או אם הופעל ב-ENV
        try_responses_api = str(model).lower().startswith("gpt-5") or str(os.getenv("OPENAI_USE_RESPONSES", "")).lower() in {"1", "true", "yes"}
        if try_responses_api:
            try:
                response = await loop.run_in_executor(
                    None,
                    partial(
                        self.openai_client.responses.create,
                        model=model,
                        input=prompt,
                        max_completion_tokens=1500,
                    ),
                )
                # חילוץ טקסט
                content = None
                try:
                    content = getattr(response, "output_text", None)
                except Exception:
                    content = None
                if not content:
                    try:
                        output = getattr(response, "output", None)
                        if output:
                            first = output[0] if isinstance(output, list) else None
                            if first is not None:
                                try:
                                    c0 = (getattr(first, "content", []) or [None])[0]
                                    content = getattr(c0, "text", None)
                                except Exception:
                                    content = None
                            if not content and isinstance(first, dict):
                                content = (((first.get("content") or [{}])[0]) or {}).get("text")
                    except Exception:
                        content = None
                tokens_used = 0
                try:
                    u = getattr(response, "usage", None)
                    if u is not None:
                        tokens_used = int((getattr(u, "input_tokens", 0) or 0) + (getattr(u, "output_tokens", 0) or 0))
                except Exception:
                    tokens_used = 0
                if not (str(content or "").strip()):
                    r = ReviewResult(provider=AIProvider.OPENAI.value, focus=focus.value)
                    r.tokens_used = tokens_used
                    r.summary = "לא התקבלה תשובה מהמודל. ודא שהמודל זמין, או נסה gpt-4o-mini."
                    r.suggestions = ["הגדר OPENAI_MODEL=gpt-4o-mini", "בדוק הרשאות ותקינות מפתח API"]
                    return r
                res = self._parse_ai_response(content, AIProvider.OPENAI.value)
                res.tokens_used = tokens_used
                return res
            except Exception as e:
                logger.error(f"OpenAI Responses API failed: {e}")
        try:
            response = await loop.run_in_executor(
                None,
                partial(
                    self.openai_client.chat.completions.create,
                    model=model,
                    messages=[{"role": "system", "content": "אתה מומחה לסקירת קוד"}, {"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=1500,
                ),
            )
        except Exception as e:
            msg = str(e)
            need_max_completion = ("max_tokens" in msg and "max_completion_tokens" in msg)
            unsupported_temp = ("temperature" in msg and "unsupported" in msg)
            # נסה Responses API אם נראה שהמודל דורש זאת
            if need_max_completion or unsupported_temp:
                try:
                    response2 = await loop.run_in_executor(
                        None,
                        partial(
                            self.openai_client.responses.create,
                            model=model,
                            input=prompt,
                            max_completion_tokens=1500,
                        ),
                    )
                    content2 = getattr(response2, "output_text", None) or ""
                    if not content2:
                        try:
                            output = getattr(response2, "output", None) or []
                            if output and isinstance(output, list):
                                first = output[0]
                                if isinstance(first, dict):
                                    content2 = (((first.get("content") or [{}])[0]) or {}).get("text") or ""
                                else:
                                    content2 = getattr(getattr(first, "content", [None])[0], "text", None) or ""
                        except Exception:
                            content2 = ""
                    tokens_used2 = 0
                    try:
                        u = getattr(response2, "usage", None)
                        if u is not None:
                            tokens_used2 = int((getattr(u, "input_tokens", 0) or 0) + (getattr(u, "output_tokens", 0) or 0))
                    except Exception:
                        tokens_used2 = 0
                    if str(content2 or "").strip():
                        res2 = self._parse_ai_response(content2, AIProvider.OPENAI.value)
                        res2.tokens_used = tokens_used2
                        return res2
                except Exception as e2:
                    logger.error(f"OpenAI Responses fallback failed: {e2}")
            try:
                if need_max_completion and unsupported_temp:
                    response = await loop.run_in_executor(
                        None,
                        partial(
                            self.openai_client.chat.completions.create,
                            model=model,
                            messages=[{"role": "system", "content": "אתה מומחה לסקירת קוד"}, {"role": "user", "content": prompt}],
                            max_completion_tokens=1500,
                        ),
                    )
                elif need_max_completion:
                    # נסה עם max_completion_tokens ושמור temperature; אם עדיין נופל על temperature – נסה בלי
                    try:
                        response = await loop.run_in_executor(
                            None,
                            partial(
                                self.openai_client.chat.completions.create,
                                model=model,
                                messages=[{"role": "system", "content": "אתה מומחה לסקירת קוד"}, {"role": "user", "content": prompt}],
                                temperature=0.3,
                                max_completion_tokens=1500,
                            ),
                        )
                    except Exception as e2:
                        if "temperature" in str(e2) and "unsupported" in str(e2):
                            response = await loop.run_in_executor(
                                None,
                                partial(
                                    self.openai_client.chat.completions.create,
                                    model=model,
                                    messages=[{"role": "system", "content": "אתה מומחה לסקירת קוד"}, {"role": "user", "content": prompt}],
                                    max_completion_tokens=1500,
                                ),
                            )
                        else:
                            raise
                elif unsupported_temp:
                    # השמט temperature ושמור max_tokens
                    response = await loop.run_in_executor(
                        None,
                        partial(
                            self.openai_client.chat.completions.create,
                            model=model,
                            messages=[{"role": "system", "content": "אתה מומחה לסקירת קוד"}, {"role": "user", "content": prompt}],
                            max_tokens=1500,
                        ),
                    )
                else:
                    raise
            except Exception:
                raise
        content = response.choices[0].message.content
        tokens_used = int(getattr(getattr(response, "usage", None), "total_tokens", 0) or 0)
        # Fallback: אם לא התקבל תוכן כלל מהמודל — נסה מודל חלופי בטוח (gpt-4o-mini)
        if not (str(content or "").strip()):
            alt_model = "gpt-4o-mini"
            try:
                alt_response = await loop.run_in_executor(
                    None,
                    partial(
                        self.openai_client.chat.completions.create,
                        model=alt_model,
                        messages=[{"role": "system", "content": "אתה מומחה לסקירת קוד"}, {"role": "user", "content": prompt}],
                        max_tokens=1500,
                    ),
                )
                alt_content = alt_response.choices[0].message.content
                if str(alt_content or "").strip():
                    content = alt_content
                    # נסה לעדכן גם מונה טוקנים אם קיים
                    try:
                        tokens_used = int(getattr(getattr(alt_response, "usage", None), "total_tokens", 0) or tokens_used)
                    except Exception:
                        pass
                else:
                    r = ReviewResult(provider=AIProvider.OPENAI.value, focus=focus.value)
                    r.tokens_used = tokens_used
                    r.summary = "לא התקבלה תשובה מהמודל. נסה שוב או הגדר OPENAI_MODEL=gpt-4o-mini."
                    r.suggestions = [
                        "נסה להריץ שוב את הסקירה",
                        "החלף OPENAI_MODEL למודל נתמך (למשל gpt-4o-mini)",
                    ]
                    return r
            except Exception:
                r = ReviewResult(provider=AIProvider.OPENAI.value, focus=focus.value)
                r.tokens_used = tokens_used
                r.summary = "שגיאה בקריאה למודל. מומלץ להגדיר OPENAI_MODEL=gpt-4o-mini ולנסות שוב."
                r.suggestions = [
                    "בדוק שהמפתח תקין והרשאות עומדות",
                    "החלף OPENAI_MODEL ל-gpt-4o-mini",
                ]
                return r
        res = self._parse_ai_response(content, AIProvider.OPENAI.value)
        res.tokens_used = tokens_used
        return res

    async def _review_with_claude(self, code: str, filename: str, focus: ReviewFocus) -> ReviewResult:
        if not self.claude_client:
            raise RuntimeError("Claude client לא זמין")
        prompt = self._build_prompt(code, filename, focus)
        message = await self.claude_client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        content = message.content[0].text
        try:
            tokens_used = int(message.usage.input_tokens) + int(message.usage.output_tokens)
        except Exception:
            tokens_used = 0
        res = self._parse_ai_response(content, AIProvider.CLAUDE.value)
        res.tokens_used = tokens_used
        return res


# אינסטנס גלובלי לשימוש קל
ai_reviewer = AICodeReviewer()

