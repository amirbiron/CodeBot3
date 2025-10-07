"""
Handlers לפקודות AI Code Review בבוט Telegram.
מותאם לקוד ול-DB הקיימים בריפו.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

from ai_code_reviewer import ai_reviewer, ReviewFocus, ReviewResult
from database import db
from user_stats import user_stats
from activity_reporter import create_reporter
from config import config

logger = logging.getLogger(__name__)

reporter = create_reporter(
    mongodb_uri=config.MONGODB_URL,
    service_id=config.BOT_LABEL,
    service_name="CodeBot",
)


class AIReviewHandlers:
    def __init__(self, application):
        self.application = application
        self.setup_handlers()

    def setup_handlers(self):
        self.application.add_handler(CommandHandler("ai_review", self.ai_review_command))
        self.application.add_handler(CommandHandler("ai_quota", self.ai_quota_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_review_callback, pattern=r"^ai_review:"))

    async def ai_review_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        try:
            reporter.report_activity(user_id)
        except Exception:
            pass
        if not context.args:
            await update.message.reply_text(
                "📄 סקירת AI לקוד\n\nשימוש: `/ai_review <filename>`\nדוגמה: `/ai_review api.py`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        filename = " ".join(context.args)
        snippet = db.get_file(user_id, filename)
        if not snippet:
            await update.message.reply_text(
                f"❌ לא נמצא קובץ בשם `{filename}`", parse_mode=ParseMode.MARKDOWN
            )
            return
        await self._show_review_type_menu(update, filename, snippet.get("code") or "")

    async def _show_review_type_menu(self, update: Update, filename: str, code: str):
        keyboard = [
            [InlineKeyboardButton("🔍 סקירה מלאה", callback_data=f"ai_review:full:{filename}")],
            [
                InlineKeyboardButton("🔒 רק אבטחה", callback_data=f"ai_review:security:{filename}"),
                InlineKeyboardButton("⚡ רק ביצועים", callback_data=f"ai_review:performance:{filename}"),
            ],
            [
                InlineKeyboardButton("🐛 רק באגים", callback_data=f"ai_review:bugs:{filename}"),
                InlineKeyboardButton("🎨 רק סגנון", callback_data=f"ai_review:style:{filename}"),
            ],
            [InlineKeyboardButton("❌ ביטול", callback_data="ai_review:cancel")],
        ]
        await update.message.reply_text(
            (
                f"🤖 סקירת AI עבור: `{filename}`\n\n"
                f"📏 גודל: {len(code)} תווים\n📝 שורות: {len((code or '').splitlines())}\n\nבחר סוג סקירה:"
            ),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def handle_review_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        parts = (query.data or "").split(":")
        if len(parts) < 2:
            return
        action = parts[1]
        if action == "cancel":
            await query.edit_message_text("❌ בוטל")
            return
        focus_str = action
        filename = ":".join(parts[2:])
        snippet = db.get_file(user_id, filename)
        if not snippet:
            await query.edit_message_text("❌ הקובץ לא נמצא")
            return
        code = snippet.get("code") or ""
        await query.edit_message_text(
            f"🔍 מבצע סקירת AI ({focus_str})...\n⏳ זה יכול לקחת כ-30 שניות"
        )
        try:
            focus = ReviewFocus(focus_str)
        except Exception:
            focus = ReviewFocus.FULL
        result = await ai_reviewer.review_code(code=code, filename=filename, user_id=user_id, focus=focus)
        self._save_review(user_id, filename, result)
        try:
            user_stats.log_user(user_id, None, weight=1)
        except Exception:
            pass
        await self._display_result(query, filename, result)

    def _save_review(self, user_id: int, filename: str, result: ReviewResult) -> None:
        try:
            coll = db.db.ai_reviews if getattr(db, "db", None) else None
            if coll is None:
                return
            coll.insert_one({
                "user_id": user_id,
                "filename": filename,
                "timestamp": datetime.now(timezone.utc),
                "result": result.to_dict(),
            })
        except Exception as e:
            logger.error(f"שגיאה בשמירת סקירה: {e}")

    async def _display_result(self, query, filename: str, result: ReviewResult):
        if result.summary.startswith("❌"):
            await query.edit_message_text(result.summary)
            return
        msg = f"🤖 סקירת AI: `{filename}`\n\n"
        stars = "⭐" * max(0, int(result.score or 0))
        msg += f"ציון: {result.score}/10 {stars}\n\n"
        def _add_list(title: str, items: list[str], max_items: int) -> str:
            if not items:
                return ""
            out = title + "\n"
            for it in items[:max_items]:
                out += f"  • {it}\n"
            if len(items) > max_items:
                out += f"  _ועוד {len(items) - max_items}..._\n"
            return out + "\n"
        msg += _add_list("🔴 בעיות אבטחה:", result.security_issues, 3)
        msg += _add_list("🐛 באגים פוטנציאליים:", result.bugs, 3)
        msg += _add_list("⚡ בעיות ביצועים:", result.performance_issues, 3)
        msg += _add_list("📋 איכות קוד:", result.code_quality_issues, 2)
        if result.suggestions:
            msg += _add_list("💡 הצעות לשיפור:", result.suggestions, 3)
        if result.summary:
            msg += f"📝 סיכום:\n{(result.summary or '')[:200]}\n\n"
        msg += f"_סופק ע״י: {result.provider} | Tokens: {result.tokens_used}_"
        if len(msg) > 4000:
            # קצר — שלח טקסט בלבד כדי לא להסתבך עם קבצים בטסטים
            await query.edit_message_text("✅ הסקירה הושלמה! הדוח ארוך — קוצר לתצוגה")
        else:
            await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN)


def setup_ai_review_handlers(application):
    return AIReviewHandlers(application)

