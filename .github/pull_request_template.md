# תבנית Pull Request

<!--
<h3>What</h3>
<p>תיאור קצר של מה שינינו.</p>

<h3>Why</h3>
<p>למה השינוי נדרש, מה הבעיה שפתרנו.</p>

<h3>Tests</h3>
<ul>
  <li>בדיקות שרצו והצליחו</li>
  <li>קישורים ל-Checks רלוונטיים</li>
  <li>סיכוני Rollback אם יש</li>
  <li>קישור ל-Docs Preview אם רלוונטי</li>
  <li>השפעה על Deploy (אם יש)</li>
  <li>CI Required Checks: 🔍 Code Quality & Security; 🧪 Unit Tests (3.11); 🧪 Unit Tests (3.12)</li>
  <li>אין סודות/PII בקוד</li>
  <li>אין מחיקות מסוכנות (ראו .cursorrules)</li>
</ul>
-->

## ✨ תיאור קצר
- מה שיניתם ולמה? (2-3 משפטים)

## 📦 שינויים עיקריים
- [ ] קוד (Backend)
- [ ] בוט טלגרם
- [ ] מסד נתונים/מיגרציות
- [ ] תיעוד (docs/)
- [ ] DevOps/CI/CD

פירוט נקודות (רשימת תבליטים):
-
-

## 🧪 בדיקות
- איך בדקתם? מה עבר? מה נשאר?
- [ ] Unit
- [ ] Integration
- [ ] Manual

## 🧪 בדיקות נדרשות ב‑PR
- 🔍 Code Quality & Security
- 🧪 Unit Tests (3.11)
- 🧪 Unit Tests (3.12)

## 📝 סוג שינוי
- [ ] feat: פיצ'ר חדש
- [ ] fix: תיקון באג
- [ ] docs: שינוי תיעוד בלבד
- [ ] refactor: שינוי קוד ללא שינוי התנהגות
- [ ] perf: שיפור ביצועים
- [ ] chore/ci: תשתית/CI
- [ ] breaking change: שינוי שובר תאימות

### דוגמאות Conventional Commits

| סוג | דוגמה להודעה | מתי להשתמש |
| --- | --- | --- |
| feat | feat: הוספת מסך הגדרות | פיצ'ר חדש למשתמש |
| fix | fix: תיקון קריסה בעת התחברות | תיקון באג מול משתמשים/פרודקשן |
| chore | chore: שדרוג Gradle ל-8.9 | תחזוקה, כלי פיתוח, housekeeping |
| docs | docs: עדכון README עם הוראות התקנה | שינויי תיעוד בלבד |
| refactor | refactor: חילוץ Repository ל-UseCases | שינוי מבני ללא שינוי התנהגות |
| test | test: הוספת בדיקות ל-LoginViewModel | הוספת/עדכון בדיקות |
| build | build: הוספת flavor staging ל-CI | שינויים בבילד/תלויות/תצורה |

## ✅ צ'קליסט
- [ ] הקוד עוקב אחרי הסגנון (Black/isort/flake8/mypy)
- [ ] בדיקות רצות ועוברות
- [ ] תיעוד עודכן (README/Docs)
- [ ] אין סודות/מפתחות בקוד
- [ ] אין מחיקות מסוכנות/פעולות על root (ראו .cursorrules)
 - [ ] הודעת הקומיט תואמת Conventional Commits (ע"פ הטבלה)
 - [ ] CHANGELOG עודכן אם נדרש
 - [ ] כל ה‑Required Checks לעיל ירוקים
 - [ ] צילום/וידאו UI מצורף אם רלוונטי

## 🧩 השפעות/סיכונים
- השפעה אפשרית על פרודקשן, ביצועים, או אבטחה:

## 🔗 קישורים
- Issues קשורים: #
- Docs Preview: <!-- הוסף כאן קישור ל-RTD Preview של ה-PR, אם קיים -->
- מסמכים/מפרטים רלוונטיים:

## 🧯 סיכון / החזרה לאחור (Rollback)
- תוכנית חזרה לאחור במקרה תקלה:
