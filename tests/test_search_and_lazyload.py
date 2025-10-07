import types
import sys
import pytest


class DummyDB:
    def __init__(self):
        self._docs = []

    def search_code(self, user_id, query="", programming_language=None, tags=None, limit=10000):
        # very naive filter for tests only
        results = list(self._docs)
        if programming_language:
            results = [d for d in results if str(d.get("programming_language", "")).lower() == programming_language]
        if tags:
            tag = tags[0]
            results = [d for d in results if tag in (d.get("tags") or [])]
        if query:
            st = query.lower()
            results = [d for d in results if st in str(d.get("file_name", "")).lower()]
        return results[:limit]


@pytest.mark.asyncio
async def test_search_flow_parsing_and_pagination(monkeypatch):
    # Arrange minimal environment
    from types import SimpleNamespace
    user_id = 123

    # Fake db
    dummy = DummyDB()
    dummy._docs = [
        {"file_name": f"util_{i}.py", "programming_language": "python", "tags": ["repo:me/app"]}
        for i in range(23)
    ]

    # Patch database import site to return our dummy
    # Inject a stub 'database' module so that main.py can import CodeSnippet/DatabaseManager/db
    mod = types.ModuleType("database")
    class _CodeSnippet:  # minimal stub for import
        pass
    class _LargeFile:  # minimal stub for import
        pass
    class _DatabaseManager:
        pass
    mod.CodeSnippet = _CodeSnippet
    mod.LargeFile = _LargeFile
    mod.DatabaseManager = _DatabaseManager
    mod.db = dummy
    monkeypatch.setitem(sys.modules, "database", mod)

    # Simulate main.handle_text_message search branch
    from main import CodeKeeperBot
    bot = CodeKeeperBot()

    class DummyMessage:
        def __init__(self, text):
            self.text = text
            self.message_id = 1

        async def reply_text(self, *_args, **_kwargs):
            return None

    class DummyUpdate:
        def __init__(self, text):
            self.message = DummyMessage(text)

        @property
        def effective_user(self):
            return SimpleNamespace(id=user_id, username="u")

    class DummyContext:
        def __init__(self):
            self.user_data = {"awaiting_search_text": True}

    # Act: query with combined filters
    update = DummyUpdate("name:util lang:python tag:repo:me/app")
    ctx = DummyContext()

    await bot.handle_text_message(update, ctx)

    # Assert: results cached and paginated (10 per page)
    files_cache = ctx.user_data.get("files_cache")
    assert files_cache is not None
    assert len(files_cache) == 10  # first page


@pytest.mark.asyncio
async def test_lazy_buttons_single_instance(monkeypatch):
    # Ensure only one Show More button is added in direct view
    from types import SimpleNamespace

    # Minimal stubs
    user_id = 1
    long_code = "\n".join([f"line {i}" for i in range(800)])
    doc = {"file_name": "a.py", "code": long_code, "programming_language": "python", "_id": "x"}

    class DummyQuery:
        def __init__(self):
            self.data = "view_direct_a.py"

        async def answer(self):
            return None

        async def edit_message_text(self, *_args, **_kwargs):
            # capture reply_markup to check buttons
            self.captured = _kwargs.get("reply_markup")

    class DummyUpdate:
        def __init__(self):
            self.callback_query = DummyQuery()

        @property
        def effective_user(self):
            return SimpleNamespace(id=user_id)

    class DummyContext:
        def __init__(self):
            self.user_data = {}

    # Patch db.get_latest_version
    # stub database module
    mod = types.ModuleType("database")
    class _LargeFile:
        pass
    mod.LargeFile = _LargeFile
    mod.db = SimpleNamespace(get_latest_version=lambda _u, _n: doc, get_large_file=lambda *_: None)
    monkeypatch.setitem(sys.modules, "database", mod)

    # Act
    from handlers.file_view import handle_view_direct_file
    update = DummyUpdate()
    ctx = DummyContext()
    await handle_view_direct_file(update, ctx)

    # Assert: only one Show More button present
    rm = update.callback_query.captured
    assert rm is not None
    rows = rm.inline_keyboard
    flat_labels = [btn.text for row in rows for btn in row]
    assert sum(1 for t in flat_labels if t.startswith("הצג עוד ")) == 1


@pytest.mark.asyncio
async def test_lazy_buttons_less_and_edges_idx(monkeypatch):
    # Prepare a long code text (more than two chunks)
    code = ("line\n" * 10000)
    file_index = "5"

    class DummyQuery:
        def __init__(self, data):
            self.data = data
            self.captured = None

        async def answer(self):
            return None

        async def edit_message_text(self, *_args, **kwargs):
            self.captured = kwargs.get("reply_markup")

    class DummyUpdate:
        def __init__(self, data):
            self.callback_query = DummyQuery(data)

        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)

    class Ctx:
        def __init__(self):
            self.user_data = {
                'files_cache': {
                    file_index: {
                        'file_name': 'b.py',
                        'code': code,
                        'programming_language': 'python',
                        'version': 1,
                    }
                },
                'files_last_page': 1,
                'files_origin': {'type': 'regular'},
            }

    from conversation_handlers import handle_callback_query

    # First expand (should show both "עוד" and "פחות")
    update = DummyUpdate(f"fv_more:idx:{file_index}:3500")
    ctx = Ctx()
    await handle_callback_query(update, ctx)
    mk = update.callback_query.captured
    assert mk is not None
    labels = [b.text for row in mk.inline_keyboard for b in row]
    assert any(t.startswith("הצג עוד ") for t in labels)
    assert any(t.startswith("הצג פחות ") for t in labels)

    # Then shrink to base (should remove "פחות" when at base)
    update2 = DummyUpdate(f"fv_less:idx:{file_index}:7000")
    await handle_callback_query(update2, ctx)
    mk2 = update2.callback_query.captured
    labels2 = [b.text for row in mk2.inline_keyboard for b in row]
    assert any(t.startswith("הצג עוד ") for t in labels2)
    assert not any(t.startswith("הצג פחות ") for t in labels2)


@pytest.mark.asyncio
async def test_search_pagination_next_prev(monkeypatch):
    # Stub database with many items
    dummy = DummyDB()
    dummy._docs = [
        {"file_name": f"proj_{i}.py", "programming_language": "python", "tags": ["repo:me/app"]}
        for i in range(23)
    ]
    mod = types.ModuleType("database")
    class _CodeSnippet:
        pass
    class _LargeFile:
        pass
    class _DatabaseManager:
        pass
    mod.CodeSnippet = _CodeSnippet
    mod.LargeFile = _LargeFile
    mod.DatabaseManager = _DatabaseManager
    mod.db = dummy
    monkeypatch.setitem(sys.modules, "database", mod)

    # Perform initial search via main
    from main import CodeKeeperBot
    bot = CodeKeeperBot()

    class Msg:
        def __init__(self, text):
            self.text = text
            self.message_id = 1

        async def reply_text(self, *_args, **_kwargs):
            return None

    class Upd:
        def __init__(self, text):
            self.message = Msg(text)

        @property
        def effective_user(self):
            return types.SimpleNamespace(id=9, username="u")

    class Ctx:
        def __init__(self):
            self.user_data = {"awaiting_search_text": True}

    u = Upd("name:proj lang:python")
    c = Ctx()
    await bot.handle_text_message(u, c)

    # Now move to page 2 via conversation handler
    from conversation_handlers import handle_callback_query

    class Q2:
        def __init__(self):
            self.data = "search_page_2"
            self.captured = None

        async def answer(self):
            return None

        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get("reply_markup")

    class U2:
        def __init__(self):
            self.callback_query = Q2()

        @property
        def effective_user(self):
            return types.SimpleNamespace(id=9)

    u2 = U2()
    await handle_callback_query(u2, c)
    rm = u2.callback_query.captured
    assert rm is not None
    labels = [b.text for row in rm.inline_keyboard for b in row]
    # Expect both next and prev on middle page
    assert any("הקודם" in t for t in labels)
    assert any("הבא" in t for t in labels)

@pytest.mark.asyncio
async def test_search_pagination_last_page_prev_only(monkeypatch):
    # Reuse DB stub with 23 results
    dummy = DummyDB()
    dummy._docs = [
        {"file_name": f"proj_{i}.py", "programming_language": "python", "tags": ["repo:me/app"]}
        for i in range(23)
    ]
    mod = types.ModuleType("database")
    class _CodeSnippet:
        pass
    class _LargeFile:
        pass
    class _DatabaseManager:
        pass
    mod.CodeSnippet = _CodeSnippet
    mod.LargeFile = _LargeFile
    mod.DatabaseManager = _DatabaseManager
    mod.db = dummy
    monkeypatch.setitem(sys.modules, "database", mod)

    from main import CodeKeeperBot
    bot = CodeKeeperBot()

    class Msg:
        def __init__(self, text):
            self.text = text
            self.message_id = 1
        async def reply_text(self, *_a, **_k):
            return None
    class Upd:
        def __init__(self, text):
            self.message = Msg(text)
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=11, username="u")
    class Ctx:
        def __init__(self):
            self.user_data = {"awaiting_search_text": True}

    u = Upd("name:proj lang:python")
    c = Ctx()
    await bot.handle_text_message(u, c)

    from conversation_handlers import handle_callback_query
    class Q3:
        def __init__(self):
            self.data = "search_page_3"
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get("reply_markup")
    class U3:
        def __init__(self):
            self.callback_query = Q3()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=11)
    u3 = U3()
    await handle_callback_query(u3, c)
    rm = u3.callback_query.captured
    assert rm is not None
    labels = [b.text for row in rm.inline_keyboard for b in row]
    assert any("הקודם" in t for t in labels)
    assert not any("הבא" in t for t in labels)

@pytest.mark.asyncio
async def test_lazy_buttons_more_less_direct(monkeypatch):
    # Stub database to force large_file path with long content
    long_code = "\n".join([f"line {i}" for i in range(12000)])
    mod = types.ModuleType("database")
    class _LargeFile: pass
    mod.LargeFile = _LargeFile
    mod.db = types.SimpleNamespace(
        get_latest_version=lambda _u, _n: None,
        get_large_file=lambda _u, _n: {
            'file_name': 'x.md',
            'content': long_code,
            'programming_language': 'markdown',
            '_id': '1'
        }
    )
    monkeypatch.setitem(sys.modules, "database", mod)

    from conversation_handlers import handle_callback_query

    class Q:
        def __init__(self, data):
            self.data = data
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get("reply_markup")
    class U:
        def __init__(self, data):
            self.callback_query = Q(data)
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=7)
    ctx = types.SimpleNamespace(user_data={})

    # Expand from 3500 -> expect both buttons
    u1 = U("fv_more:direct:x.md:3500")
    await handle_callback_query(u1, ctx)
    rm1 = u1.callback_query.captured
    labels1 = [b.text for row in rm1.inline_keyboard for b in row]
    assert any(t.startswith("הצג עוד ") for t in labels1)
    assert any(t.startswith("הצג פחות ") for t in labels1)

    # Shrink to base -> expect no "פחות"
    u2 = U("fv_less:direct:x.md:7000")
    await handle_callback_query(u2, ctx)
    rm2 = u2.callback_query.captured
    labels2 = [b.text for row in rm2.inline_keyboard for b in row]
    assert any(t.startswith("הצג עוד ") for t in labels2)
    assert not any(t.startswith("הצג פחות ") for t in labels2)

@pytest.mark.asyncio
async def test_by_repo_pagination_basic(monkeypatch):
    # Stub db.get_user_files_by_repo to serve two pages
    items = [
        {"file_name": f"f_{i}.py", "programming_language": "python"}
        for i in range(15)
    ]
    def get_user_files_by_repo(_uid, _tag, page=1, per_page=10):
        start = (page - 1) * per_page
        end = min(start + per_page, len(items))
        return items[start:end], len(items)
    mod = types.ModuleType("database")
    mod.db = types.SimpleNamespace(get_user_files_by_repo=get_user_files_by_repo)
    monkeypatch.setitem(sys.modules, "database", mod)

    from conversation_handlers import handle_callback_query

    class Q:
        def __init__(self, data):
            self.data = data
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get("reply_markup")
    class U:
        def __init__(self, data):
            self.callback_query = Q(data)
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=5)
    ctx = types.SimpleNamespace(user_data={})

    # First page
    u1 = U("by_repo:repo:me/app")
    await handle_callback_query(u1, ctx)
    rm1 = u1.callback_query.captured
    assert rm1 is not None
    # Move to page 2 regardless of button text/format

    # Second page
    u2 = U("by_repo_page:repo:me/app:2")
    await handle_callback_query(u2, ctx)
    rm2 = u2.callback_query.captured
    # Ensure page 2 shows items and files_cache updated to indices starting at 10
    cache = ctx.user_data.get('files_cache')
    assert cache is not None
    assert any(k == '10' for k in cache.keys())


@pytest.mark.asyncio
async def test_view_file_show_more_idx_button_and_back_by_repo(monkeypatch):
    # Arrange a long code in files_cache and origin by_repo
    long_code = "x" * 8000
    file_index = "3"

    class Q:
        def __init__(self):
            self.data = f"view_{file_index}"
            self.captured = None
            self.captured_text = None
            self.captured_mode = None
        async def answer(self):
            return None
        async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None, **_):
            self.captured = reply_markup
            self.captured_text = text
            self.captured_mode = parse_mode
    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    ctx = types.SimpleNamespace(user_data={
        'files_cache': {
            file_index: {
                'file_name': 'repo_file.py',
                'code': long_code,
                'programming_language': 'python',
                'version': 1,
                'description': ''
            }
        },
        'files_last_page': 2,
        'files_origin': {'type': 'by_repo', 'tag': 'repo:me/app'},
    })

    from handlers.file_view import handle_view_file
    await handle_view_file(U(), ctx)
    kb = U().callback_query.captured  # new instance; capture from previous
    kb = ctx.user_data.get('last_kb') if hasattr(ctx.user_data, 'last_kb') else None
    # If not stored, access from the query we called
    kb = U().callback_query.captured if kb is None else kb
    # For reliability, re-run and access directly
    u = U()
    await handle_view_file(u, ctx)
    rm = u.callback_query.captured
    assert rm is not None
    labels = [b.text for row in rm.inline_keyboard for b in row]
    assert any(t.startswith("הצג עוד ") for t in labels)
    back_targets = [b.callback_data for row in rm.inline_keyboard for b in row]
    assert any(str(cd) == "by_repo:repo:me/app" for cd in back_targets)


@pytest.mark.asyncio
async def test_view_direct_file_large_markdown_includes_note(monkeypatch):
    # Stub database to return a large markdown file via large_files fallback
    mod = types.ModuleType("database")
    class _LargeFile: pass
    mod.LargeFile = _LargeFile
    content = "# Title\n" + ("line\n" * 4000)
    mod.db = types.SimpleNamespace(
        get_latest_version=lambda *_: None,
        get_large_file=lambda *_: {
            'file_name': 'doc.md',
            'content': content,
            'programming_language': 'markdown',
            'description': '',
            '_id': 'abc'
        }
    )
    monkeypatch.setitem(sys.modules, "database", mod)

    class Q:
        def __init__(self):
            self.data = "view_direct_doc.md"
            self.captured = None
            self.captured_text = None
            self.captured_mode = None
        async def answer(self):
            return None
        async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None, **_):
            self.captured = reply_markup
            self.captured_text = text
            self.captured_mode = parse_mode
    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    from handlers.file_view import handle_view_direct_file
    u = U()
    ctx = types.SimpleNamespace(user_data={})
    await handle_view_direct_file(u, ctx)
    # Expect HTML mode and large-file note
    assert u.callback_query.captured_mode == 'HTML'
    assert "זה קובץ גדול" in (u.callback_query.captured_text or "")


@pytest.mark.asyncio
async def test_handle_download_file_back_index(monkeypatch):
    # Prepare context and query for index download
    class Q:
        def __init__(self):
            self.data = "dl_7"
            self.captured = None
            self.message = types.SimpleNamespace(reply_document=self._reply_document)
        async def answer(self):
            return None
        async def _reply_document(self, **_):
            return None
        async def edit_message_text(self, text=None, reply_markup=None, **_):
            self.captured = reply_markup
    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    ctx = types.SimpleNamespace(user_data={
        'files_cache': {
            '7': {
                'file_name': 'd.py',
                'code': 'print(1)',
                'programming_language': 'python'
            }
        }
    })
    from handlers.file_view import handle_download_file
    u = U()
    await handle_download_file(u, ctx)
    rm = u.callback_query.captured
    assert rm is not None
    targets = [b.callback_data for row in rm.inline_keyboard for b in row]
    assert any(cd == 'file_7' for cd in targets)


@pytest.mark.asyncio
async def test_search_no_results_stays_awaiting(monkeypatch):
    # Stub empty search
    mod = types.ModuleType("database")
    class _CodeSnippet: pass
    class _LargeFile: pass
    class _DatabaseManager: pass
    mod.CodeSnippet = _CodeSnippet
    mod.LargeFile = _LargeFile
    mod.DatabaseManager = _DatabaseManager
    mod.db = types.SimpleNamespace(search_code=lambda *args, **kwargs: [])
    monkeypatch.setitem(sys.modules, "database", mod)

    from main import CodeKeeperBot
    bot = CodeKeeperBot()

    class Msg:
        def __init__(self, text):
            self.text = text
            self.message_id = 1
        async def reply_text(self, *_a, **_k):
            return None
    class Upd:
        def __init__(self, text):
            self.message = Msg(text)
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=2, username='u')
    class Ctx:
        def __init__(self):
            self.user_data = {"awaiting_search_text": True}
    u = Upd("name:xyz lang:python")
    c = Ctx()
    await bot.handle_text_message(u, c)
    assert c.user_data.get('awaiting_search_text') is True


@pytest.mark.asyncio
async def test_view_direct_file_large_markdown_with_note(monkeypatch):
    # Large markdown + note should render HTML and include note text
    mod = types.ModuleType("database")
    class _LargeFile: pass
    mod.LargeFile = _LargeFile
    content = ("# H1\n" * 3000)
    note = "כאן הערה"
    mod.db = types.SimpleNamespace(
        get_latest_version=lambda *_: None,
        get_large_file=lambda *_: {
            'file_name': 'doc.md',
            'content': content,
            'programming_language': 'markdown',
            'description': note,
            '_id': 'id2'
        }
    )
    monkeypatch.setitem(sys.modules, "database", mod)

    class Q:
        def __init__(self):
            self.data = "view_direct_doc.md"
            self.captured_text = None
            self.captured_mode = None
        async def answer(self):
            return None
        async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None, **_):
            self.captured_text = text
            self.captured_mode = parse_mode
    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    from handlers.file_view import handle_view_direct_file
    u = U()
    ctx = types.SimpleNamespace(user_data={})
    await handle_view_direct_file(u, ctx)
    assert u.callback_query.captured_mode == 'HTML'
    assert "כאן הערה" in (u.callback_query.captured_text or "")


@pytest.mark.asyncio
async def test_safe_edit_message_text_ignores_not_modified(monkeypatch):
    # TelegramUtils.safe_edit_message_text shouldn't raise on 'message is not modified'
    from utils import TelegramUtils

    class BR(Exception):
        pass
    import telegram.error
    # monkeypatch telegram.error.BadRequest to our BR subclass instance raising
    class FakeBadRequest(telegram.error.BadRequest):
        pass

    class Q:
        def __init__(self):
            pass
        async def edit_message_text(self, *a, **k):
            raise FakeBadRequest("Message is not modified")

    # Should not raise
    await TelegramUtils.safe_edit_message_text(Q(), "text")


@pytest.mark.asyncio
async def test_fv_more_less_bounds_no_crash(monkeypatch):
    # Bounds: attempting to 'less' near base and 'more' near end shouldn't crash
    long_code = "\n".join([f"line {i}" for i in range(1000)])
    # db stub for direct mode
    mod = types.ModuleType("database")
    mod.db = types.SimpleNamespace(
        get_latest_version=lambda *_: {'file_name': 'z.py', 'code': long_code, 'programming_language': 'python', '_id': '1'},
        get_large_file=lambda *_: None
    )
    monkeypatch.setitem(sys.modules, "database", mod)

    from conversation_handlers import handle_callback_query
    class Q:
        def __init__(self, data):
            self.data = data
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get('reply_markup')
    class U:
        def __init__(self, data):
            self.callback_query = Q(data)
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    ctx = types.SimpleNamespace(user_data={})

    # less at base (offset 3500 -> back to 3500), but our code shorter—shouldn't crash
    await handle_callback_query(U("fv_less:direct:z.py:3500"), ctx)
    # more near end
    await handle_callback_query(U("fv_more:direct:z.py:3500"), ctx)


@pytest.mark.asyncio
async def test_fv_more_regular_origin_back_to_regular(monkeypatch):
    # Arrange long code under files_cache and origin regular
    code = "\n".join([f"r{i}" for i in range(10000)])
    idx = "12"
    class Q:
        def __init__(self, data):
            self.data = data
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get('reply_markup')
    class U:
        def __init__(self, data):
            self.callback_query = Q(data)
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    ctx = types.SimpleNamespace(user_data={
        'files_cache': {idx: {'file_name': 'r.py', 'code': code, 'programming_language': 'python', 'version': 1}},
        'files_last_page': 4,
        'files_origin': {'type': 'regular'}
    })
    from conversation_handlers import handle_callback_query
    u = U(f"fv_more:idx:{idx}:3500")
    await handle_callback_query(u, ctx)
    rm = u.callback_query.captured
    assert rm is not None
    cbs = [b.callback_data for row in rm.inline_keyboard for b in row]
    assert any(cb == 'files_page_4' for cb in cbs)


@pytest.mark.asyncio
async def test_back_after_view_fallsback_to_db(monkeypatch):
    # No last_save_success — should fetch from DB and build menu
    fname = 'fb.py'
    mod = types.ModuleType("database")
    mod.db = types.SimpleNamespace(get_latest_version=lambda _u, _n: {
        'file_name': fname,
        'programming_language': 'python',
        'description': '',
        '_id': 'X'
    })
    monkeypatch.setitem(sys.modules, "database", mod)
    from conversation_handlers import handle_callback_query
    class Q:
        def __init__(self):
            self.data = f"back_after_view:{fname}"
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get('reply_markup')
    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=2)
    ctx = types.SimpleNamespace(user_data={})
    u = U()
    await handle_callback_query(u, ctx)
    rm = u.callback_query.captured
    assert rm is not None
    callbacks = [b.callback_data for row in rm.inline_keyboard for b in row]
    assert any(cb == f"view_direct_{fname}" for cb in callbacks)


@pytest.mark.asyncio
async def test_view_direct_file_non_markdown_markdown_mode(monkeypatch):
    # Stub db to return a small python file
    mod = types.ModuleType("database")
    class _LargeFile: pass
    mod.LargeFile = _LargeFile
    mod.db = types.SimpleNamespace(
        get_latest_version=lambda *_: {
            'file_name': 's.py',
            'code': 'print(1)',
            'programming_language': 'python',
            'description': '',
            '_id': 'id1'
        },
        get_large_file=lambda *_: None
    )
    monkeypatch.setitem(sys.modules, "database", mod)

    class Q:
        def __init__(self):
            self.data = "view_direct_s.py"
            self.captured_mode = None
            self.captured_text = None
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None, **_):
            self.captured_mode = parse_mode
            self.captured_text = text
            self.captured = reply_markup
    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    from handlers.file_view import handle_view_direct_file
    u = U()
    ctx = types.SimpleNamespace(user_data={})
    await handle_view_direct_file(u, ctx)
    assert u.callback_query.captured_mode == 'Markdown'
    assert "זה קובץ גדול" not in (u.callback_query.captured_text or "")


@pytest.mark.asyncio
async def test_back_after_view_menu_builds(monkeypatch):
    # Ensure back_after_view builds menu from last_save_success
    fname = 'ret.py'
    ctx = types.SimpleNamespace(user_data={
        'last_save_success': {
            'file_name': fname,
            'language': 'python',
            'note': '',
            'file_id': 'OID'
        }
    })
    from conversation_handlers import handle_callback_query
    class Q:
        def __init__(self):
            self.data = f"back_after_view:{fname}"
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get('reply_markup')
    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)
    u = U()
    await handle_callback_query(u, ctx)
    rm = u.callback_query.captured
    assert rm is not None
    callbacks = [b.callback_data for row in rm.inline_keyboard for b in row]
    assert any(cb == f"view_direct_{fname}" for cb in callbacks)


@pytest.mark.asyncio
async def test_handle_view_file_html_respects_4096(monkeypatch):
    # Ensure handle_view_file trims safely after HTML escaping
    import types

    long_code = "<" * 8000  # expands significantly when escaped (&lt;)
    file_index = "7"

    class Q:
        def __init__(self):
            self.data = f"view_{file_index}"
            self.captured = None
            self.captured_text = None
            self.captured_mode = None
        async def answer(self):
            return None
        async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None, **_):
            self.captured = reply_markup
            self.captured_text = text
            self.captured_mode = parse_mode

    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)

    ctx = types.SimpleNamespace(user_data={
        'files_cache': {
            file_index: {
                'file_name': 'f.html',
                'code': long_code,
                'programming_language': 'html',
                'version': 1,
                'description': ''
            }
        },
        'files_last_page': 1,
        'files_origin': {'type': 'regular'},
    })

    from handlers.file_view import handle_view_file
    u = U()
    await handle_view_file(u, ctx)
    assert u.callback_query.captured_mode == 'HTML'
    assert u.callback_query.captured_text is not None
    assert len(u.callback_query.captured_text) <= 4096
    assert '<pre><code>' in u.callback_query.captured_text


@pytest.mark.asyncio
async def test_handle_view_version_html_respects_4096(monkeypatch):
    # Ensure handle_view_version trims safely after HTML escaping
    import types, sys

    big = "<" * 10000
    mod = types.ModuleType("database")
    mod.db = types.SimpleNamespace(
        get_version=lambda _u, _n, _v: {
            'code': big,
            'programming_language': 'html'
        },
        get_latest_version=lambda _u, _n: {'version': 1}
    )
    monkeypatch.setitem(sys.modules, "database", mod)

    from conversation_handlers import handle_view_version

    class Q:
        def __init__(self):
            self.data = 'view_version_1_f.html'
            self.captured_text = None
            self.captured_mode = None
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, text=None, reply_markup=None, parse_mode=None, **_):
            self.captured_text = text
            self.captured_mode = parse_mode
            self.captured = reply_markup

    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)

    u = U()
    ctx = types.SimpleNamespace(user_data={})
    await handle_view_version(u, ctx)
    assert u.callback_query.captured_mode == 'HTML'
    assert u.callback_query.captured_text is not None
    assert len(u.callback_query.captured_text) <= 4096
    assert '<pre><code>' in u.callback_query.captured_text


@pytest.mark.asyncio
async def test_receive_new_name_prefers_id_when_available(monkeypatch):
    # After rename, the 'view code' button should prefer view_direct_id when fid exists
    import types, sys

    mod = types.ModuleType("database")
    mod.db = types.SimpleNamespace(
        rename_file=lambda *_: True,
        get_latest_version=lambda _u, name: {
            '_id': 'OID123',
            'file_name': name,
            'code': 'print(1)',
            'programming_language': 'python'
        }
    )
    monkeypatch.setitem(sys.modules, "database", mod)

    class Msg:
        def __init__(self):
            self.text = 'new.py'
            self.captured = None
        async def reply_text(self, *_a, **kw):
            self.captured = kw.get('reply_markup')
            return None

    class U:
        def __init__(self):
            self.message = Msg()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=5)

    ctx = types.SimpleNamespace(user_data={
        'editing_file_data': {'file_name': 'old.py'},
        'editing_file_name': 'old.py'
    })

    from handlers.file_view import receive_new_name
    u = U()
    await receive_new_name(u, ctx)
    rm = u.message.captured
    assert rm is not None
    callbacks = [b.callback_data for row in rm.inline_keyboard for b in row]
    assert any(cb == 'view_direct_id:OID123' for cb in callbacks)


@pytest.mark.asyncio
async def test_handle_clone_direct_prefers_id(monkeypatch):
    # After clone direct, prefer id in the 'view code' button if new doc has _id
    import types, sys

    class FakeDB:
        def __init__(self):
            self.saved = []
        def get_latest_version(self, _u, name):
            if name == 'src.py':
                return {'file_name': 'src.py', 'code': 'x', 'programming_language': 'python', '_id': 'SRC'}
            # for new names
            return {'file_name': name, '_id': 'NEWID'}
        def save_code_snippet(self, snippet):
            self.saved.append(snippet)
            return True

    db = FakeDB()
    mod = types.ModuleType("database")
    mod.db = db
    monkeypatch.setitem(sys.modules, "database", mod)

    from handlers.file_view import handle_clone_direct

    class Q:
        def __init__(self):
            self.data = 'clone_direct_src.py'
            self.captured = None
        async def answer(self):
            return None
        async def edit_message_text(self, *_a, **kw):
            self.captured = kw.get('reply_markup')
            return None

    class U:
        def __init__(self):
            self.callback_query = Q()
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=1)

    u = U()
    ctx = types.SimpleNamespace(user_data={})
    await handle_clone_direct(u, ctx)
    rm = u.callback_query.captured
    assert rm is not None
    cbs = [b.callback_data for row in rm.inline_keyboard for b in row]
    assert any(cb == 'view_direct_id:NEWID' for cb in cbs)


@pytest.mark.asyncio
async def test_code_hint_when_text_looks_like_code(monkeypatch):
    # Ensure code hint path replies
    from main import CodeKeeperBot
    bot = CodeKeeperBot()
    called = {'flag': False}
    class Msg:
        def __init__(self, text):
            self.text = text
            self.message_id = 1
        async def reply_text(self, *_a, **_k):
            called['flag'] = True
            return None
    class Upd:
        def __init__(self, text):
            self.message = Msg(text)
        @property
        def effective_user(self):
            return types.SimpleNamespace(id=3, username='u')
    class Ctx:
        def __init__(self):
            self.user_data = {}
    await bot.handle_text_message(Upd("def f():\n    return 1\n"), Ctx())
    assert called['flag'] is True
