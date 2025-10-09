# 📋 פיצ'ר: Templates - תבניות קוד מותאמות אישית

## 📋 תיאור כללי

מערכת תבניות שמאפשרת למשתמשים לשמור קטעי קוד כתבניות לשימוש חוזר. הפיצ'ר חוסך זמן רב ומבטיח עקביות בקוד.

### 🎯 מטרות הפיצ'ר
- שמירת קטעי קוד נפוצים לשימוש חוזר
- יצירת פרויקטים חדשים במהירות
- עקביות בסגנון קידוד
- שיתוף תבניות בין פרויקטים

### 👤 תרחישי שימוש
1. **Backend Developer**: שומר תבניות של Flask/FastAPI endpoints
2. **Frontend Developer**: תבניות של React components
3. **DevOps**: תבניות של Docker, CI/CD configs
4. **Student**: תבניות מהקורסים ללמידה חוזרת

---

## 🗄️ מבנה Database

### קולקציה חדשה: code_templates

```python
# מבנה מסמך בקולקציה code_templates

{
    "_id": ObjectId("..."),
    "template_id": "unique_template_id_123",  # מזהה ייחודי
    "user_id": 123456789,                     # בעלים
    "template_name": "flask_rest_api",        # שם התבנית
    "display_name": "Flask REST API Starter", # שם תצוגה
    "description": "תבנית בסיסית ל-REST API עם Flask",
    "category": "backend",                    # קטגוריה
    "programming_language": "python",         # שפת התכנות
    "code": "# Flask API Template\n...",     # הקוד עצמו
    "tags": ["flask", "api", "rest"],        # תגיות
    "is_public": false,                       # האם ציבורית
    "variables": [                            # משתנים להחלפה
        {
            "name": "PROJECT_NAME",
            "placeholder": "my_project",
            "description": "שם הפרויקט"
        },
        {
            "name": "PORT",
            "placeholder": "5000",
            "description": "פורט להרצה"
        }
    ],
    "usage_count": 5,                         # כמה פעמים נוצל
    "created_at": ISODate("2024-10-09T10:00:00Z"),
    "updated_at": ISODate("2024-10-09T10:00:00Z"),
    "last_used_at": ISODate("2024-10-09T12:00:00Z")
}
```

### אינדקסים

```python
# ב-database/manager.py - __init__

# יצירת קולקציה וואינדקסים לתבניות
self.templates_collection = self.db.code_templates

self.templates_collection.create_index([
    ("user_id", 1),
    ("template_name", 1)
], unique=True)  # שם תבנית ייחודי לכל משתמש

self.templates_collection.create_index([
    ("user_id", 1),
    ("category", 1)
])

self.templates_collection.create_index([
    ("is_public", 1),
    ("category", 1),
    ("usage_count", -1)
])  # לתבניות ציבוריות פופולריות
```

---

## 💻 מימוש קוד

### 1. מודל Template (database/models.py)

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional

@dataclass
class TemplateVariable:
    """משתנה בתבנית"""
    name: str
    placeholder: str
    description: str = ""

@dataclass
class CodeTemplate:
    """מודל תבנית קוד"""
    template_id: str
    user_id: int
    template_name: str
    display_name: str
    description: str
    category: str
    programming_language: str
    code: str
    tags: List[str] = field(default_factory=list)
    is_public: bool = False
    variables: List[TemplateVariable] = field(default_factory=list)
    usage_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        """המרה למילון למסד נתונים"""
        return {
            "template_id": self.template_id,
            "user_id": self.user_id,
            "template_name": self.template_name,
            "display_name": self.display_name,
            "description": self.description,
            "category": self.category,
            "programming_language": self.programming_language,
            "code": self.code,
            "tags": self.tags,
            "is_public": self.is_public,
            "variables": [
                {
                    "name": v.name,
                    "placeholder": v.placeholder,
                    "description": v.description
                } for v in self.variables
            ],
            "usage_count": self.usage_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at
        }
```

---

### 2. פונקציות Database (database/manager.py)

```python
import secrets
from typing import List, Dict, Optional

def save_template(
    self,
    user_id: int,
    template_name: str,
    display_name: str,
    code: str,
    programming_language: str,
    description: str = "",
    category: str = "general",
    tags: List[str] = None,
    variables: List[Dict] = None
) -> Optional[str]:
    """
    שמירת תבנית חדשה
    
    Returns:
        template_id אם הצליח, None אם נכשל
    """
    try:
        # בדיקה אם שם התבנית קיים
        existing = self.templates_collection.find_one({
            "user_id": user_id,
            "template_name": template_name
        })
        
        if existing:
            logger.warning(f"תבנית {template_name} כבר קיימת")
            return None
        
        # יצירת ID ייחודי
        template_id = f"tpl_{secrets.token_urlsafe(16)}"
        
        template_data = {
            "template_id": template_id,
            "user_id": user_id,
            "template_name": template_name,
            "display_name": display_name,
            "description": description,
            "category": category,
            "programming_language": programming_language,
            "code": code,
            "tags": tags or [],
            "is_public": False,
            "variables": variables or [],
            "usage_count": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "last_used_at": None
        }
        
        self.templates_collection.insert_one(template_data)
        logger.info(f"תבנית {template_name} נשמרה בהצלחה")
        return template_id
        
    except Exception as e:
        logger.error(f"שגיאה בשמירת תבנית: {e}")
        return None


def get_user_templates(
    self,
    user_id: int,
    category: str = None,
    limit: int = 50
) -> List[Dict]:
    """קבלת תבניות של משתמש"""
    try:
        query = {"user_id": user_id}
        if category:
            query["category"] = category
        
        templates = list(
            self.templates_collection.find(query)
            .sort("last_used_at", -1)
            .limit(limit)
        )
        
        # המרת ObjectId למחרוזת
        for t in templates:
            t["_id"] = str(t["_id"])
        
        return templates
        
    except Exception as e:
        logger.error(f"שגיאה בקבלת תבניות: {e}")
        return []


def get_template(self, user_id: int, template_name: str) -> Optional[Dict]:
    """קבלת תבנית ספציפית"""
    try:
        template = self.templates_collection.find_one({
            "user_id": user_id,
            "template_name": template_name
        })
        
        if template:
            template["_id"] = str(template["_id"])
        
        return template
        
    except Exception as e:
        logger.error(f"שגיאה בקבלת תבנית: {e}")
        return None


def use_template(
    self,
    user_id: int,
    template_name: str,
    target_file_name: str,
    replacements: Dict[str, str] = None
) -> Optional[str]:
    """
    שימוש בתבנית - יצירת קובץ חדש מהתבנית
    
    Args:
        replacements: מילון של משתנים → ערכים להחלפה
    
    Returns:
        הקוד המעובד
    """
    try:
        template = self.get_template(user_id, template_name)
        if not template:
            logger.warning(f"תבנית {template_name} לא נמצאה")
            return None
        
        code = template["code"]
        
        # החלפת משתנים
        if replacements and template.get("variables"):
            for var in template["variables"]:
                var_name = var["name"]
                placeholder = "{{" + var_name + "}}"
                
                if var_name in replacements:
                    code = code.replace(placeholder, replacements[var_name])
                else:
                    # השתמש ב-placeholder ברירת מחדל
                    code = code.replace(placeholder, var.get("placeholder", ""))
        
        # עדכון מונה שימושים
        self.templates_collection.update_one(
            {"user_id": user_id, "template_name": template_name},
            {
                "$inc": {"usage_count": 1},
                "$set": {
                    "last_used_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc)
                }
            }
        )
        
        # שמירת הקובץ החדש
        self.save_code_snippet(
            user_id=user_id,
            file_name=target_file_name,
            code=code,
            programming_language=template["programming_language"],
            tags=template.get("tags", []) + ["from_template"],
            note=f"נוצר מתבנית: {template['display_name']}"
        )
        
        logger.info(f"תבנית {template_name} נוצלה ליצירת {target_file_name}")
        return code
        
    except Exception as e:
        logger.error(f"שגיאה בשימוש בתבנית: {e}")
        return None


def delete_template(self, user_id: int, template_name: str) -> bool:
    """מחיקת תבנית"""
    try:
        result = self.templates_collection.delete_one({
            "user_id": user_id,
            "template_name": template_name
        })
        
        if result.deleted_count > 0:
            logger.info(f"תבנית {template_name} נמחקה")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"שגיאה במחיקת תבנית: {e}")
        return False


def get_template_categories(self, user_id: int) -> List[Dict[str, int]]:
    """קבלת קטגוריות וספירת תבניות בכל אחת"""
    try:
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {
                "_id": "$category",
                "count": {"$sum": 1}
            }},
            {"$sort": {"count": -1}}
        ]
        
        results = list(self.templates_collection.aggregate(pipeline))
        
        categories = [
            {"category": r["_id"], "count": r["count"]}
            for r in results
        ]
        
        return categories
        
    except Exception as e:
        logger.error(f"שגיאה בקבלת קטגוריות: {e}")
        return []
```

---

### 3. Handler לתבניות (templates_handler.py)

צור קובץ חדש: `templates_handler.py`

```python
"""
מטפל בתבניות - Templates Handler
"""

import logging
import re
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

from database import db
from utils import get_language_emoji
from activity_reporter import create_reporter

logger = logging.getLogger(__name__)

# שלבי שיחה
TEMPLATE_NAME, TEMPLATE_CODE, TEMPLATE_VARS = range(3)
USE_TEMPLATE_NAME, USE_TEMPLATE_VARS = range(2)

reporter = create_reporter(
    mongodb_uri="mongodb+srv://mumin:M43M2TFgLfGvhBwY@muminai.tm6x81b.mongodb.net/?retryWrites=true&w=majority&appName=muminAI",
    service_id="srv-d3ilh4vfte5s7392s000",
    service_name="CodeBot3"
)


async def template_save_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    פקודה: /template_save <file_name>
    התחלת תהליך שמירת תבנית מקובץ קיים
    """
    reporter.report_activity(update.effective_user.id)
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "📋 <b>שמירת תבנית מקובץ קיים</b>\n\n"
            "שימוש: <code>/template_save &lt;file_name&gt;</code>\n\n"
            "דוגמה:\n"
            "<code>/template_save flask_api.py</code>\n\n"
            "הקובץ ישמר כתבנית לשימוש חוזר.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END
    
    file_name = " ".join(context.args)
    
    # בדיקה אם הקובץ קיים
    snippet = db.get_code_snippet(user_id, file_name)
    if not snippet:
        await update.message.reply_text(
            f"❌ הקובץ <code>{file_name}</code> לא נמצא.\n"
            "שלח <code>/list</code> לרשימת הקבצים שלך.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END
    
    # שמירה בהקשר
    context.user_data["template_source_file"] = file_name
    context.user_data["template_code"] = snippet["code"]
    context.user_data["template_language"] = snippet["programming_language"]
    context.user_data["template_tags"] = snippet.get("tags", [])
    
    await update.message.reply_text(
        f"✅ מצוין! נשתמש בקובץ <code>{file_name}</code>\n\n"
        f"📝 עכשיו שלח שם לתבנית (באנגלית, ללא רווחים):\n\n"
        f"דוגמה: <code>flask_rest_api</code>",
        parse_mode=ParseMode.HTML
    )
    
    return TEMPLATE_NAME


async def template_save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """קבלת שם התבנית"""
    user_id = update.effective_user.id
    template_name = update.message.text.strip().lower()
    
    # ולידציה - רק אותיות, מספרים וקו תחתון
    if not re.match(r'^[a-z0-9_]+$', template_name):
        await update.message.reply_text(
            "❌ שם התבנית חייב להכיל רק אותיות אנגליות, מספרים וקו תחתון (_)\n\n"
            "נסה שוב:"
        )
        return TEMPLATE_NAME
    
    # בדיקה אם התבנית כבר קיימת
    existing = db.get_template(user_id, template_name)
    if existing:
        await update.message.reply_text(
            f"⚠️ תבנית בשם <code>{template_name}</code> כבר קיימת.\n\n"
            "בחר שם אחר:",
            parse_mode=ParseMode.HTML
        )
        return TEMPLATE_NAME
    
    context.user_data["template_name"] = template_name
    
    await update.message.reply_text(
        f"✅ שם התבנית: <code>{template_name}</code>\n\n"
        f"📝 עכשיו שלח תיאור קצר לתבנית:\n\n"
        f"דוגמה: <code>תבנית בסיסית ל-REST API עם Flask</code>",
        parse_mode=ParseMode.HTML
    )
    
    return TEMPLATE_CODE


async def template_save_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """קבלת תיאור ושמירת התבנית"""
    user_id = update.effective_user.id
    description = update.message.text.strip()
    
    template_name = context.user_data["template_name"]
    code = context.user_data["template_code"]
    language = context.user_data["template_language"]
    tags = context.user_data.get("template_tags", [])
    
    # זיהוי משתנים בקוד ({{VAR_NAME}})
    variables = []
    var_pattern = r'\{\{([A-Z_]+)\}\}'
    found_vars = re.findall(var_pattern, code)
    
    if found_vars:
        for var_name in set(found_vars):
            variables.append({
                "name": var_name,
                "placeholder": var_name.lower(),
                "description": f"ערך עבור {var_name}"
            })
    
    # שמירה
    template_id = db.save_template(
        user_id=user_id,
        template_name=template_name,
        display_name=template_name.replace("_", " ").title(),
        code=code,
        programming_language=language,
        description=description,
        category="general",
        tags=tags,
        variables=variables
    )
    
    if not template_id:
        await update.message.reply_text(
            "❌ שגיאה בשמירת התבנית. נסה שוב מאוחר יותר."
        )
        return ConversationHandler.END
    
    # הודעת הצלחה
    message = (
        f"✅ <b>תבנית נשמרה בהצלחה!</b>\n\n"
        f"📋 שם: <code>{template_name}</code>\n"
        f"📝 תיאור: {description}\n"
        f"{get_language_emoji(language)} שפה: {language}\n"
    )
    
    if variables:
        message += f"\n🔧 משתנים שזוהו:\n"
        for var in variables:
            message += f"   • <code>{{{{{var['name']}}}}}</code>\n"
    
    message += (
        f"\n💡 להשתמש בתבנית:\n"
        f"<code>/template_use {template_name} target_file.py</code>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📋 רשימת תבניות", callback_data="templates_list"),
            InlineKeyboardButton("🔧 השתמש עכשיו", callback_data=f"use_tpl_{template_name}")
        ]
    ]
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # ניקוי הקשר
    context.user_data.clear()
    
    return ConversationHandler.END


async def template_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    פקודה: /templates
    הצגת כל התבניות
    """
    reporter.report_activity(update.effective_user.id)
    user_id = update.effective_user.id
    
    # בדיקה אם יש סינון לפי קטגוריה
    category = context.args[0] if context.args else None
    
    templates = db.get_user_templates(user_id, category=category)
    
    if not templates:
        message = (
            "💭 <b>אין לך תבניות עדיין</b>\n\n"
            "💡 צור תבנית מקובץ קיים:\n"
            "<code>/template_save &lt;file_name&gt;</code>\n\n"
            "דוגמה:\n"
            "<code>/template_save api.py</code>"
        )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
        return
    
    # קבלת קטגוריות
    categories = db.get_template_categories(user_id)
    
    # בניית הודעה
    message_lines = [
        "📋 <b>התבניות שלך</b>",
        f"📊 סה״כ: {len(templates)} תבניות"
    ]
    
    if categories:
        message_lines.append("\n📂 קטגוריות:")
        for cat in categories:
            message_lines.append(f"   • {cat['category']}: {cat['count']}")
    
    message_lines.append("")
    
    for idx, tpl in enumerate(templates[:10], 1):
        name = tpl["template_name"]
        display = tpl.get("display_name", name)
        lang = tpl["programming_language"]
        emoji = get_language_emoji(lang)
        usage = tpl.get("usage_count", 0)
        desc = tpl.get("description", "")
        
        line = f"{idx}. 📋 <code>{name}</code>"
        if display != name:
            line += f"\n   📌 {display}"
        line += f"\n   {emoji} {lang} • שימושים: {usage}"
        if desc:
            desc_short = desc[:60] + "..." if len(desc) > 60 else desc
            line += f"\n   💬 {desc_short}"
        
        message_lines.append(line)
    
    if len(templates) > 10:
        message_lines.append(f"\n➕ ועוד {len(templates) - 10} תבניות...")
    
    message = "\n\n".join(message_lines)
    
    # כפתורים
    keyboard = []
    
    # שורה ראשונה: פעולות
    keyboard.append([
        InlineKeyboardButton("🔍 חיפוש", callback_data="templates_search"),
        InlineKeyboardButton("📊 סטטיסטיקה", callback_data="templates_stats")
    ])
    
    # כפתורים לתבניות (עד 6)
    tpl_buttons = []
    for tpl in templates[:6]:
        name = tpl["template_name"]
        tpl_buttons.append(
            InlineKeyboardButton(
                f"📋 {name[:15]}",
                callback_data=f"show_tpl_{name}"
            )
        )
    
    for i in range(0, len(tpl_buttons), 2):
        keyboard.append(tpl_buttons[i:i+2])
    
    await update.message.reply_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def template_use_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    פקודה: /template_use <template_name> <target_file>
    שימוש בתבנית
    """
    reporter.report_activity(update.effective_user.id)
    user_id = update.effective_user.id
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "🔧 <b>שימוש בתבנית</b>\n\n"
            "שימוש: <code>/template_use &lt;template_name&gt; &lt;target_file&gt;</code>\n\n"
            "דוגמה:\n"
            "<code>/template_use flask_api my_api.py</code>\n\n"
            "התבנית תיצור קובץ חדש עם הקוד.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END
    
    template_name = context.args[0]
    target_file = " ".join(context.args[1:])
    
    # בדיקה אם התבנית קיימת
    template = db.get_template(user_id, template_name)
    if not template:
        await update.message.reply_text(
            f"❌ תבנית <code>{template_name}</code> לא נמצאה.\n\n"
            "שלח <code>/templates</code> לרשימת התבניות שלך.",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END
    
    # בדיקה אם יש משתנים
    variables = template.get("variables", [])
    
    if not variables:
        # אין משתנים - צור ישירות
        code = db.use_template(user_id, template_name, target_file)
        
        if code:
            await update.message.reply_text(
                f"✅ <b>קובץ נוצר מתבנית!</b>\n\n"
                f"📁 קובץ חדש: <code>{target_file}</code>\n"
                f"📋 תבנית: {template['display_name']}\n"
                f"📏 גודל: {len(code)} תווים\n\n"
                f"שלח <code>/show {target_file}</code> לצפייה.",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text("❌ שגיאה ביצירת הקובץ")
        
        return ConversationHandler.END
    
    # יש משתנים - בקש ערכים
    context.user_data["template_name"] = template_name
    context.user_data["target_file"] = target_file
    context.user_data["variables"] = variables
    context.user_data["replacements"] = {}
    context.user_data["current_var_idx"] = 0
    
    # שאל על המשתנה הראשון
    var = variables[0]
    await update.message.reply_text(
        f"🔧 <b>הגדרת משתנים</b>\n\n"
        f"משתנה 1/{len(variables)}: <code>{{{{{var['name']}}}}}</code>\n"
        f"📝 {var['description']}\n\n"
        f"💡 ברירת מחדל: <code>{var['placeholder']}</code>\n\n"
        f"שלח ערך או <code>skip</code> לדילוג:",
        parse_mode=ParseMode.HTML
    )
    
    return USE_TEMPLATE_VARS


async def template_use_variables(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """קבלת ערכי משתנים"""
    user_id = update.effective_user.id
    value = update.message.text.strip()
    
    variables = context.user_data["variables"]
    current_idx = context.user_data["current_var_idx"]
    var = variables[current_idx]
    
    # שמירת הערך
    if value.lower() != "skip":
        context.user_data["replacements"][var["name"]] = value
    
    # עבור למשתנה הבא
    current_idx += 1
    context.user_data["current_var_idx"] = current_idx
    
    if current_idx < len(variables):
        # עוד משתנים
        var = variables[current_idx]
        await update.message.reply_text(
            f"🔧 משתנה {current_idx + 1}/{len(variables)}: <code>{{{{{var['name']}}}}}</code>\n"
            f"📝 {var['description']}\n\n"
            f"💡 ברירת מחדל: <code>{var['placeholder']}</code>\n\n"
            f"שלח ערך או <code>skip</code> לדילוג:",
            parse_mode=ParseMode.HTML
        )
        return USE_TEMPLATE_VARS
    
    # סיימנו עם המשתנים - צור קובץ
    template_name = context.user_data["template_name"]
    target_file = context.user_data["target_file"]
    replacements = context.user_data["replacements"]
    
    code = db.use_template(user_id, template_name, target_file, replacements)
    
    if code:
        message = (
            f"✅ <b>קובץ נוצר מתבנית!</b>\n\n"
            f"📁 קובץ חדש: <code>{target_file}</code>\n"
            f"📋 תבנית: {template_name}\n"
            f"📏 גודל: {len(code)} תווים\n"
        )
        
        if replacements:
            message += "\n🔧 משתנים שהוחלפו:\n"
            for key, val in replacements.items():
                message += f"   • {key} → {val}\n"
        
        message += f"\nשלח <code>/show {target_file}</code> לצפייה."
        
        keyboard = [[
            InlineKeyboardButton("📋 הצג קובץ", callback_data=f"show_{target_file}")
        ]]
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("❌ שגיאה ביצירת הקובץ")
    
    context.user_data.clear()
    return ConversationHandler.END


async def template_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מטפל בלחיצות על כפתורים"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data.startswith("show_tpl_"):
        # הצגת תבנית
        template_name = data.replace("show_tpl_", "")
        template = db.get_template(user_id, template_name)
        
        if not template:
            await query.edit_message_text("❌ תבנית לא נמצאה")
            return
        
        message = (
            f"📋 <b>{template['display_name']}</b>\n\n"
            f"🔤 שם: <code>{template['template_name']}</code>\n"
            f"{get_language_emoji(template['programming_language'])} שפה: {template['programming_language']}\n"
            f"📝 {template['description']}\n"
            f"🎯 שימושים: {template['usage_count']}\n"
        )
        
        if template.get("tags"):
            tags_str = " ".join([f"#{t}" for t in template["tags"]])
            message += f"🏷️ {tags_str}\n"
        
        if template.get("variables"):
            message += f"\n🔧 משתנים:\n"
            for var in template["variables"]:
                message += f"   • <code>{{{{{var['name']}}}}}</code> - {var['description']}\n"
        
        keyboard = [
            [
                InlineKeyboardButton("🔧 השתמש", callback_data=f"use_tpl_{template_name}"),
                InlineKeyboardButton("🗑️ מחק", callback_data=f"del_tpl_{template_name}")
            ],
            [
                InlineKeyboardButton("🔙 חזור", callback_data="templates_list")
            ]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data.startswith("del_tpl_"):
        template_name = data.replace("del_tpl_", "")
        
        if db.delete_template(user_id, template_name):
            await query.edit_message_text(
                f"✅ תבנית <code>{template_name}</code> נמחקה",
                parse_mode=ParseMode.HTML
            )
        else:
            await query.edit_message_text("❌ שגיאה במחיקה")


def setup_templates_handlers(application):
    """רישום handlers"""
    
    # ConversationHandler לשמירת תבנית
    save_conv = ConversationHandler(
        entry_points=[CommandHandler("template_save", template_save_start)],
        states={
            TEMPLATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_save_name)],
            TEMPLATE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_save_description)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    
    # ConversationHandler לשימוש בתבנית
    use_conv = ConversationHandler(
        entry_points=[CommandHandler("template_use", template_use_start)],
        states={
            USE_TEMPLATE_VARS: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_use_variables)]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )
    
    application.add_handler(save_conv)
    application.add_handler(use_conv)
    application.add_handler(CommandHandler("templates", template_list_command))
    application.add_handler(CallbackQueryHandler(
        template_callback_handler,
        pattern="^(show_tpl_|del_tpl_|use_tpl_)"
    ))
```

---

### 4. שילוב ב-main.py

```python
from templates_handler import setup_templates_handlers

# בפונקציה main():
setup_templates_handlers(application)
```

---

## 🎨 עיצוב UI/UX

### שמירת תבנית
```
משתמש: /template_save api.py

בוט: ✅ מצוין! נשתמש בקובץ api.py

📝 עכשיו שלח שם לתבנית (באנגלית, ללא רווחים):

דוגמה: flask_rest_api

משתמש: flask_api

בוט: ✅ שם התבנית: flask_api

📝 עכשיו שלח תיאור קצר לתבנית:

משתמש: API בסיסי עם Flask

בוט: ✅ תבנית נשמרה בהצלחה!

📋 שם: flask_api
📝 תיאור: API בסיסי עם Flask
🐍 שפה: Python

💡 להשתמש בתבנית:
/template_use flask_api target.py

[📋 רשימת תבניות] [🔧 השתמש עכשיו]
```

---

## ✅ רשימת משימות למימוש

- [ ] יצירת קולקציה code_templates
- [ ] מודל CodeTemplate
- [ ] פונקציות DB
- [ ] Handler לשמירה
- [ ] Handler לשימוש
- [ ] רשימת תבניות
- [ ] מחיקת תבניות
- [ ] משתנים בתבניות
- [ ] קטגוריות
- [ ] סטטיסטיקות

---

**סיום מדריך Templates** 📋
