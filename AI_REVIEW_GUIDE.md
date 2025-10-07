# 📘 הנחיות שימוש והטמעה – AI Code Review

מסמך קצר שמסביר מה נוסף בריפו, איך מפעילים, ואילו משתני סביבה צריכים להיות מוגדרים.

---

## מה חדש
- קובץ `ai_code_reviewer.py`: מנוע סקירת קוד עם תמיכה ב־Ollama / OpenAI / Claude, כולל קיטום קוד, Rate Limiting ו־Cache.
- קובץ `ai_review_handlers.py`: פקודות Telegram חדשות:
  - `/ai_review <filename>` — פתיחת תפריט סקירה וביצוע סקירה.
  - `/ai_quota` — הצגת מכסת סקירות נותרת למשתמש.
- `config.py`: נוספו שדות קונפיג לשירותי ה־AI ומגבלות שימוש.
- `main.py`: חיבור ה־handlers החדשים באמצעות `setup_ai_review_handlers`.

---

## משתני סביבה (ENV)
ניתן להגדיר בקובץ `.env` או במשתני סביבה של הסביבה המארחת.

חובה קיימים כבר בפרויקט:
- `BOT_TOKEN`
- `MONGODB_URL`

חדשים לאפשרויות AI:
- `AI_PROVIDER` — ספק ה־AI לשימוש: `ollama` (ברירת מחדל) / `openai` / `claude`.
- `OLLAMA_URL` — ברירת מחדל: `http://localhost:11434`.
- `OLLAMA_MODEL` — ברירת מחדל: `deepseek-coder:6.7b`.
- `OPENAI_API_KEY` — אם בוחרים `AI_PROVIDER=openai`.
- `ANTHROPIC_API_KEY` — אם בוחרים `AI_PROVIDER=claude`.
- `AI_REVIEW_MAX_PER_DAY` — ברירת מחדל: `10`.
- `AI_REVIEW_MAX_PER_HOUR` — ברירת מחדל: `3`.

דוגמה `.env`:
```bash
# ----------------------------------
# חובה קיימים
BOT_TOKEN=123:ABC
MONGODB_URL=mongodb://localhost:27017/code_keeper_bot

# ----------------------------------
# AI Review
AI_PROVIDER=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-coder:6.7b
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=...
AI_REVIEW_MAX_PER_DAY=10
AI_REVIEW_MAX_PER_HOUR=3
```

---

## שימוש
1) ודאו שהבוט רץ כרגיל עם `BOT_TOKEN` ו־`MONGODB_URL` תקינים.
2) בחרו ספק AI:
   - לשימוש מקומי וחינמי: `AI_PROVIDER=ollama` והפעילו Ollama מקומית (`ollama serve`).
   - לשימוש ב־OpenAI/Claude: הגדירו מפתחות מתאימים.
3) שלחו לבוט:
   - `/ai_review <filename>` — בחרו סוג סקירה והמתינו ~20–40 שניות.
   - `/ai_quota` — לקבלת מכסה נותרת.

תוצאת הסקירה נשמרת גם ב־Mongo תחת הקולקציה `ai_reviews`.

---

## הערות מימוש
- Cache: שימוש ב־`cache_manager.set(key, value, expire_seconds=...)`.
- Rate Limiting: ברירת מחדל 10 ליום, 3 לשעה — ניתן לשינוי ב־ENV.
- קיטום קוד: עד 15K תווים או 500 שורות; שמירה על ההתחלה והסוף.
- פרומפט: מחייב JSON; יש fallback לפענוח טקסט חופשי במקרה של חריגה.
- תלות: אין צורך לעדכן `requirements.txt` אם עובדים עם Ollama; ל־OpenAI/Claude יש להתקין `openai`/`anthropic` ידנית אם רוצים שימוש בהם.

---

## תקלות נפוצות
- Ollama לא רץ: הפעילו `ollama serve` וודאו שהמודל קיים (`ollama pull <model>`).
- מפתחות חסרים: ודאו שהוגדרו `OPENAI_API_KEY` או `ANTHROPIC_API_KEY` לפי הצורך.
- חריגת זמן: נסו שוב או החליפו מודל/ספק.

---

בהצלחה! 🚀