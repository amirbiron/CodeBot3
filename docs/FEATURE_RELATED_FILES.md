# 🗂️ פיצ'ר: Related Files - קבצים קשורים

## 📋 תיאור כללי

מערכת זיהוי אוטומטי של קבצים קשורים על בסיס תלויות, דמיון בתוכן, תגיות משותפות וזמני עריכה. הפיצ'ר מספק הקשר טוב יותר ומסייע במציאת קוד רלוונטי.

### 🎯 מטרות הפיצ'ר
- זיהוי אוטומטי של קבצים קשורים
- הקשר טוב יותר בעבודה על הקוד
- מציאת קוד רלוונטי במהירות
- הבנת מבנה הפרויקט

### 👤 תרחישי שימוש
1. **Developer עובד על API**: רואה קבצים קשורים (models, tests, config)
2. **Refactoring**: מציאת כל הקבצים שמשתמשים בפונקציה
3. **Learning**: מציאת דוגמאות דומות לקוד שכתבת
4. **Debug**: מציאת קבצים שעודכנו באותו זמן

---

## 🧠 אלגוריתמי זיהוי

### 1. תלויות ישירות (Direct Dependencies)
זיהוי imports בקוד:

```python
# api.py
from database import User, Session  # → תלות ישירה ב-database.py
from config import API_KEY           # → תלות ישירה ב-config.py
import utils                         # → תלות ישירה ב-utils.py
```

### 2. דמיון בתוכן (Content Similarity)
השוואת קוד על בסיס:
- שמות פונקציות/מחלקות משותפים
- imports דומים
- מילות מפתח חוזרות

### 3. תגיות משותפות (Shared Tags)
קבצים עם תגיות דומות:
```
api.py: #api #backend #flask
auth.py: #api #backend #auth
models.py: #backend #database
```

### 4. זמני עריכה קרובים (Temporal Proximity)
קבצים שנערכו באותו פרק זמן (24-48 שעות)

---

## 💻 מימוש קוד

### 1. מנוע זיהוי (related_files_engine.py)

צור קובץ חדש: `related_files_engine.py`

```python
"""
מנוע זיהוי קבצים קשורים
Related Files Detection Engine
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Set, Tuple

from fuzzywuzzy import fuzz
from database import db

logger = logging.getLogger(__name__)


class RelatedFilesEngine:
    """מנוע לזיהוי קבצים קשורים"""
    
    def __init__(self):
        self.import_patterns = {
            'python': [
                r'from\s+(\w+(?:\.\w+)*)\s+import',
                r'import\s+(\w+(?:\.\w+)*)'
            ],
            'javascript': [
                r'import\s+.*\s+from\s+[\'"](.+?)[\'"]',
                r'require\([\'"](.+?)[\'"]\)'
            ],
            'java': [
                r'import\s+([\w.]+);'
            ],
            'go': [
                r'import\s+["\'](.+?)["\']'
            ]
        }
    
    def find_related_files(
        self,
        user_id: int,
        file_name: str,
        max_results: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        מציאת כל הקבצים הקשורים
        
        Returns:
            מילון עם קטגוריות: dependencies, similar, same_tags, temporal
        """
        try:
            # קבלת הקובץ המקורי
            snippet = db.get_code_snippet(user_id, file_name)
            if not snippet:
                logger.warning(f"קובץ {file_name} לא נמצא")
                return {}
            
            results = {
                "dependencies": [],
                "similar": [],
                "same_tags": [],
                "temporal": []
            }
            
            # 1. תלויות ישירות
            results["dependencies"] = self._find_dependencies(
                user_id, snippet, max_results
            )
            
            # 2. דמיון בתוכן
            results["similar"] = self._find_similar_content(
                user_id, file_name, snippet, max_results
            )
            
            # 3. תגיות משותפות
            results["same_tags"] = self._find_by_tags(
                user_id, file_name, snippet, max_results
            )
            
            # 4. זמני עריכה קרובים
            results["temporal"] = self._find_by_time(
                user_id, file_name, snippet, max_results
            )
            
            return results
            
        except Exception as e:
            logger.error(f"שגיאה בחיפוש קבצים קשורים: {e}")
            return {}
    
    def _find_dependencies(
        self,
        user_id: int,
        snippet: Dict,
        max_results: int
    ) -> List[Dict]:
        """זיהוי תלויות ישירות"""
        try:
            code = snippet.get("code", "")
            language = snippet.get("programming_language", "").lower()
            
            # קבלת patterns לשפה
            patterns = self.import_patterns.get(language, [])
            if not patterns:
                return []
            
            # חילוץ imports
            imported_modules = set()
            for pattern in patterns:
                matches = re.findall(pattern, code, re.MULTILINE)
                imported_modules.update(matches)
            
            if not imported_modules:
                return []
            
            # חיפוש קבצים תואמים
            all_files = db.get_user_files(user_id, limit=1000)
            dependencies = []
            
            for file_data in all_files:
                target_name = file_data["file_name"]
                
                # בדיקה אם שם הקובץ תואם ל-import
                for module in imported_modules:
                    # המרת module path לשם קובץ
                    possible_names = [
                        f"{module}.py",
                        f"{module.split('.')[-1]}.py",
                        f"{module}.js",
                        f"{module.split('.')[-1]}.js"
                    ]
                    
                    if target_name in possible_names or module in target_name:
                        dependencies.append({
                            "file_name": target_name,
                            "programming_language": file_data.get("programming_language", ""),
                            "import_name": module,
                            "score": 1.0  # תלות ישירה = ציון מלא
                        })
                        break
            
            return dependencies[:max_results]
            
        except Exception as e:
            logger.error(f"שגיאה בזיהוי תלויות: {e}")
            return []
    
    def _find_similar_content(
        self,
        user_id: int,
        file_name: str,
        snippet: Dict,
        max_results: int
    ) -> List[Dict]:
        """מציאת קבצים דומים בתוכן"""
        try:
            code = snippet.get("code", "")
            language = snippet.get("programming_language", "")
            
            # חילוץ מאפיינים
            source_features = self._extract_features(code)
            
            # קבלת קבצים באותה שפה
            all_files = db.get_user_files(user_id, limit=1000)
            similar_files = []
            
            for file_data in all_files:
                target_name = file_data["file_name"]
                if target_name == file_name:
                    continue
                
                # רק קבצים באותה שפה
                if file_data.get("programming_language") != language:
                    continue
                
                target_code = file_data.get("code", "")
                target_features = self._extract_features(target_code)
                
                # חישוב דמיון
                similarity = self._calculate_similarity(
                    source_features, target_features
                )
                
                if similarity > 0.3:  # סף מינימלי
                    similar_files.append({
                        "file_name": target_name,
                        "programming_language": language,
                        "similarity": similarity,
                        "score": similarity
                    })
            
            # מיון לפי דמיון
            similar_files.sort(key=lambda x: x["score"], reverse=True)
            
            return similar_files[:max_results]
            
        except Exception as e:
            logger.error(f"שגיאה בחיפוש דמיון: {e}")
            return []
    
    def _extract_features(self, code: str) -> Dict[str, Set[str]]:
        """חילוץ מאפיינים מקוד"""
        features = {
            "functions": set(),
            "classes": set(),
            "imports": set(),
            "keywords": set()
        }
        
        try:
            # פונקציות (Python, JS)
            func_pattern = r'(?:def|function|async\s+function)\s+(\w+)'
            features["functions"] = set(re.findall(func_pattern, code))
            
            # מחלקות
            class_pattern = r'class\s+(\w+)'
            features["classes"] = set(re.findall(class_pattern, code))
            
            # imports
            import_pattern = r'(?:import|from|require)\s+(\w+)'
            features["imports"] = set(re.findall(import_pattern, code))
            
            # מילות מפתח נפוצות
            words = re.findall(r'\b\w{4,}\b', code.lower())
            features["keywords"] = set([w for w in words if len(w) >= 4])
            
        except Exception as e:
            logger.error(f"שגיאה בחילוץ מאפיינים: {e}")
        
        return features
    
    def _calculate_similarity(
        self,
        features1: Dict[str, Set[str]],
        features2: Dict[str, Set[str]]
    ) -> float:
        """חישוב דמיון בין שני קבצים"""
        try:
            scores = []
            
            # דמיון בפונקציות (משקל גבוה)
            if features1["functions"] and features2["functions"]:
                common = features1["functions"] & features2["functions"]
                total = features1["functions"] | features2["functions"]
                func_score = len(common) / len(total) if total else 0
                scores.append(func_score * 2)  # משקל כפול
            
            # דמיון במחלקות
            if features1["classes"] and features2["classes"]:
                common = features1["classes"] & features2["classes"]
                total = features1["classes"] | features2["classes"]
                class_score = len(common) / len(total) if total else 0
                scores.append(class_score * 1.5)
            
            # דמיון ב-imports
            if features1["imports"] and features2["imports"]:
                common = features1["imports"] & features2["imports"]
                total = features1["imports"] | features2["imports"]
                import_score = len(common) / len(total) if total else 0
                scores.append(import_score * 1.2)
            
            # דמיון במילות מפתח
            if features1["keywords"] and features2["keywords"]:
                # רק 50 מילות המפתח הנפוצות
                kw1 = set(list(features1["keywords"])[:50])
                kw2 = set(list(features2["keywords"])[:50])
                common = kw1 & kw2
                total = kw1 | kw2
                kw_score = len(common) / len(total) if total else 0
                scores.append(kw_score)
            
            # ממוצע משוקלל
            return sum(scores) / len(scores) if scores else 0
            
        except Exception as e:
            logger.error(f"שגיאה בחישוב דמיון: {e}")
            return 0
    
    def _find_by_tags(
        self,
        user_id: int,
        file_name: str,
        snippet: Dict,
        max_results: int
    ) -> List[Dict]:
        """מציאת קבצים עם תגיות משותפות"""
        try:
            tags = snippet.get("tags", [])
            if not tags:
                return []
            
            # חיפוש קבצים עם תגיות חופפות
            all_files = db.get_user_files(user_id, limit=1000)
            tagged_files = []
            
            source_tags = set(tags)
            
            for file_data in all_files:
                target_name = file_data["file_name"]
                if target_name == file_name:
                    continue
                
                target_tags = set(file_data.get("tags", []))
                if not target_tags:
                    continue
                
                # חישוב חפיפה
                common = source_tags & target_tags
                if not common:
                    continue
                
                overlap = len(common) / len(source_tags | target_tags)
                
                tagged_files.append({
                    "file_name": target_name,
                    "programming_language": file_data.get("programming_language", ""),
                    "common_tags": list(common),
                    "overlap": overlap,
                    "score": overlap
                })
            
            tagged_files.sort(key=lambda x: x["score"], reverse=True)
            return tagged_files[:max_results]
            
        except Exception as e:
            logger.error(f"שגיאה בחיפוש לפי תגיות: {e}")
            return []
    
    def _find_by_time(
        self,
        user_id: int,
        file_name: str,
        snippet: Dict,
        max_results: int
    ) -> List[Dict]:
        """מציאת קבצים שנערכו בזמן דומה"""
        try:
            updated_at = snippet.get("updated_at")
            if not updated_at:
                return []
            
            # חלון זמן של 48 שעות
            time_window = timedelta(hours=48)
            start_time = updated_at - time_window
            end_time = updated_at + time_window
            
            # חיפוש קבצים בחלון זמן
            all_files = db.get_user_files(user_id, limit=1000)
            temporal_files = []
            
            for file_data in all_files:
                target_name = file_data["file_name"]
                if target_name == file_name:
                    continue
                
                target_time = file_data.get("updated_at")
                if not target_time:
                    continue
                
                # בדיקה אם בחלון זמן
                if start_time <= target_time <= end_time:
                    # חישוב קרבה בזמן
                    time_diff = abs((target_time - updated_at).total_seconds())
                    hours_diff = time_diff / 3600
                    proximity = max(0, 1 - (hours_diff / 48))  # ציון לפי קרבה
                    
                    temporal_files.append({
                        "file_name": target_name,
                        "programming_language": file_data.get("programming_language", ""),
                        "updated_at": target_time,
                        "hours_diff": hours_diff,
                        "score": proximity
                    })
            
            temporal_files.sort(key=lambda x: x["score"], reverse=True)
            return temporal_files[:max_results]
            
        except Exception as e:
            logger.error(f"שגיאה בחיפוש לפי זמן: {e}")
            return []


# יצירת instance גלובלי
related_engine = RelatedFilesEngine()
```

---

### 2. Handler (related_files_handler.py)

```python
"""
מטפל בקבצים קשורים - Related Files Handler
"""

import logging
from typing import Dict, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from database import db
from utils import get_language_emoji
from related_files_engine import related_engine
from activity_reporter import create_reporter

logger = logging.getLogger(__name__)

reporter = create_reporter(
    mongodb_uri="mongodb+srv://mumin:M43M2TFgLfGvhBwY@muminai.tm6x81b.mongodb.net/?retryWrites=true&w=majority&appName=muminAI",
    service_id="srv-d3ilh4vfte5s7392s000",
    service_name="CodeBot3"
)


async def related_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    פקודה: /related <file_name>
    הצגת קבצים קשורים
    """
    reporter.report_activity(update.effective_user.id)
    user_id = update.effective_user.id
    
    if not context.args:
        await update.message.reply_text(
            "🗂️ <b>קבצים קשורים</b>\n\n"
            "שימוש: <code>/related &lt;file_name&gt;</code>\n\n"
            "דוגמה:\n"
            "<code>/related api.py</code>\n\n"
            "הבוט ימצא קבצים קשורים על בסיס:\n"
            "• תלויות (imports)\n"
            "• דמיון בתוכן\n"
            "• תגיות משותפות\n"
            "• זמני עריכה קרובים",
            parse_mode=ParseMode.HTML
        )
        return
    
    file_name = " ".join(context.args)
    
    # בדיקה אם הקובץ קיים
    snippet = db.get_code_snippet(user_id, file_name)
    if not snippet:
        await update.message.reply_text(
            f"❌ הקובץ <code>{file_name}</code> לא נמצא.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # הודעת המתנה
    wait_msg = await update.message.reply_text(
        "🔍 מחפש קבצים קשורים..."
    )
    
    # חיפוש
    related = related_engine.find_related_files(user_id, file_name, max_results=8)
    
    # בניית הודעה
    message_lines = [
        f"🗂️ <b>קבצים קשורים ל-{file_name}</b>\n"
    ]
    
    has_results = False
    
    # תלויות ישירות
    if related.get("dependencies"):
        has_results = True
        message_lines.append("📌 <b>תלויות ישירות:</b>")
        for dep in related["dependencies"][:5]:
            name = dep["file_name"]
            import_name = dep.get("import_name", "")
            emoji = get_language_emoji(dep.get("programming_language", ""))
            message_lines.append(
                f"   {emoji} <code>{name}</code>\n"
                f"      └─ import: <code>{import_name}</code>"
            )
        message_lines.append("")
    
    # דמיון בתוכן
    if related.get("similar"):
        has_results = True
        message_lines.append("🎯 <b>דומים בתוכן:</b>")
        for sim in related["similar"][:5]:
            name = sim["file_name"]
            score = sim.get("similarity", 0)
            emoji = get_language_emoji(sim.get("programming_language", ""))
            percentage = int(score * 100)
            message_lines.append(
                f"   {emoji} <code>{name}</code> ({percentage}% דמיון)"
            )
        message_lines.append("")
    
    # תגיות משותפות
    if related.get("same_tags"):
        has_results = True
        message_lines.append("🏷️ <b>תגיות משותפות:</b>")
        for tagged in related["same_tags"][:5]:
            name = tagged["file_name"]
            common = tagged.get("common_tags", [])
            emoji = get_language_emoji(tagged.get("programming_language", ""))
            tags_str = " ".join([f"#{t}" for t in common[:3]])
            message_lines.append(
                f"   {emoji} <code>{name}</code>\n"
                f"      └─ {tags_str}"
            )
        message_lines.append("")
    
    # זמני עריכה
    if related.get("temporal"):
        has_results = True
        message_lines.append("⏱️ <b>נערכו באותו זמן:</b>")
        for temp in related["temporal"][:5]:
            name = temp["file_name"]
            hours = temp.get("hours_diff", 0)
            emoji = get_language_emoji(temp.get("programming_language", ""))
            time_str = f"{int(hours)} שעות" if hours >= 1 else "פחות משעה"
            message_lines.append(
                f"   {emoji} <code>{name}</code> (הפרש: {time_str})"
            )
        message_lines.append("")
    
    if not has_results:
        message_lines.append("💭 לא נמצאו קבצים קשורים.")
    
    message = "\n".join(message_lines)
    
    # כפתורים
    keyboard = []
    
    # כפתורים לקבצים הקשורים הראשונים
    all_related = []
    for category in ["dependencies", "similar", "same_tags", "temporal"]:
        all_related.extend(related.get(category, []))
    
    # הסרת כפילויות
    seen = set()
    unique_related = []
    for item in all_related:
        name = item["file_name"]
        if name not in seen:
            seen.add(name)
            unique_related.append(item)
    
    # כפתורים (עד 6)
    file_buttons = []
    for item in unique_related[:6]:
        name = item["file_name"]
        file_buttons.append(
            InlineKeyboardButton(
                f"📄 {name[:18]}",
                callback_data=f"show_{name}"
            )
        )
    
    for i in range(0, len(file_buttons), 2):
        keyboard.append(file_buttons[i:i+2])
    
    # כפתור רענון
    keyboard.append([
        InlineKeyboardButton("🔄 רענן חיפוש", callback_data=f"related_refresh_{file_name}")
    ])
    
    await wait_msg.edit_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def related_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מטפל בלחיצות"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("related_refresh_"):
        file_name = data.replace("related_refresh_", "")
        user_id = update.effective_user.id
        
        await query.edit_message_text("🔍 מרענן...")
        
        related = related_engine.find_related_files(user_id, file_name, max_results=8)
        
        # בניית הודעה מחדש (כמו ב-related_command)
        # ...


def setup_related_files_handlers(application):
    """רישום handlers"""
    application.add_handler(CommandHandler("related", related_command))
    application.add_handler(CallbackQueryHandler(
        related_callback_handler,
        pattern="^related_refresh_"
    ))
```

---

### 3. שילוב ב-main.py

```python
from related_files_handler import setup_related_files_handlers

setup_related_files_handlers(application)
```

---

### 4. שילוב בהצגת קובץ

```python
# ב-show_command ב-bot_handlers.py:

keyboard = [
    # ... כפתורים קיימים
    [
        InlineKeyboardButton("🗂️ קבצים קשורים", callback_data=f"related_{file_name}"),
        InlineKeyboardButton("📊 ניתוח", callback_data=f"analyze_{file_name}")
    ],
    # ...
]
```

---

## 🎨 עיצוב UI/UX

```
🗂️ קבצים קשורים ל-api.py

📌 תלויות ישירות:
   🐍 database.py
      └─ import: database
   🐍 config.py
      └─ import: config

🎯 דומים בתוכן:
   🐍 auth_api.py (75% דמיון)
   🐍 user_api.py (68% דמיון)

🏷️ תגיות משותפות:
   🐍 models.py
      └─ #api #backend
   🐍 tests.py
      └─ #api #tests

⏱️ נערכו באותו זמן:
   🐍 requirements.txt (2 שעות)
   🐍 README.md (3 שעות)

[📄 database.py] [📄 auth_api.py]
[📄 models.py] [📄 tests.py]
[🔄 רענן חיפוש]
```

---

## ✅ רשימת משימות

- [ ] מנוע זיהוי תלויות
- [ ] מנוע דמיון בתוכן
- [ ] זיהוי לפי תגיות
- [ [ זיהוי לפי זמן
- [ ] Handler לתצוגה
- [ ] אופטימיזציה (caching)
- [ ] תמיכה בשפות נוספות
- [ ] שילוב בUI

---

**סיום מדריך Related Files** 🗂️
