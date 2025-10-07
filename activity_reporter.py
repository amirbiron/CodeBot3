"""
קובץ פשוט לדיווח פעילות - העתק את הקובץ הזה לכל בוט
"""
try:
    from pymongo import MongoClient  # type: ignore
    _HAS_PYMONGO = True
except Exception:
    MongoClient = None  # type: ignore
    _HAS_PYMONGO = False
from datetime import datetime, timezone


class SimpleActivityReporter:
    def __init__(self, mongodb_uri, service_id, service_name=None):
        """
        mongodb_uri: חיבור למונגו (אותו מהבוט המרכזי)
        service_id: מזהה השירות ב-Render
        service_name: שם הבוט (אופציונלי)
        """
        try:
            if not _HAS_PYMONGO:
                raise RuntimeError("pymongo not available")
            self.client = MongoClient(mongodb_uri, tz_aware=True, tzinfo=timezone.utc)
            self.db = self.client["render_bot_monitor"]
            self.service_id = service_id
            self.service_name = service_name or service_id
            self.connected = True
        except Exception:
            self.connected = False
            # שקט בסביבת בדיקות/ללא pymongo
            pass
    
    def report_activity(self, user_id):
        """דיווח פעילות פשוט"""
        if not self.connected:
            return
        
        try:
            now = datetime.now(timezone.utc)
            
            # עדכון אינטראקציית המשתמש
            self.db.user_interactions.update_one(
                {"service_id": self.service_id, "user_id": user_id},
                {
                    "$set": {"last_interaction": now},
                    "$inc": {"interaction_count": 1},
                    "$setOnInsert": {"created_at": now}
                },
                upsert=True
            )
            
            # עדכון פעילות השירות
            self.db.service_activity.update_one(
                {"_id": self.service_id},
                {
                    "$set": {
                        "last_user_activity": now,
                        "service_name": self.service_name,
                        "updated_at": now
                    },
                    "$setOnInsert": {
                        "created_at": now,
                        "status": "active",
                        "total_users": 0,
                        "suspend_count": 0
                    }
                },
                upsert=True
            )
            
        except Exception:
            # שקט - אל תיכשל את הבוט אם יש בעיה
            pass

# דוגמה לשימוש קל
def create_reporter(mongodb_uri, service_id, service_name=None):
    """יצירת reporter פשוט"""
    return SimpleActivityReporter(mongodb_uri, service_id, service_name)