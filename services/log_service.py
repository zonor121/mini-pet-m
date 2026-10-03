from datetime import datetime
from services.supabase_client import supabase_admin


def log_status_change(registration_id, old_status, new_status, changed_by_user_id):
    """Записывает изменение статуса в таблицу registration_logs."""
    try:
        supabase_admin.table("registration_logs").insert({
            "registration_id": registration_id,
            "old_status": old_status,
            "new_status": new_status,
            "changed_by": changed_by_user_id,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        print(f"Log error: {e}")
        # Не прерываем основной процесс, если лог не записался