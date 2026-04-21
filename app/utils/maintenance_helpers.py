from datetime import datetime, timezone
from app.models.maintenance import MaintenanceSettings
from app.extensions import db

def get_maintenance_state():
    m = MaintenanceSettings.get()
    now = datetime.utcnow()

    # Auto-activate if scheduled start has passed
    if not m.is_active and m.scheduled_start and now >= m.scheduled_start:
        m.is_active = True
        db.session.commit()

    # Auto-end only if the flag is set
    if m.is_active and m.auto_end and m.estimated_end and now >= m.estimated_end:
        m.is_active       = False
        m.scheduled_start = None
        m.estimated_end   = None
        db.session.commit()

    seconds_until_start = None
    if not m.is_active and m.scheduled_start:
        diff = (m.scheduled_start - now).total_seconds()
        seconds_until_start = max(0, int(diff))

    seconds_until_end = None
    if m.is_active and m.show_countdown and m.estimated_end:
        diff = (m.estimated_end - now).total_seconds()
        seconds_until_end = max(0, int(diff))

    return {
        "is_active":           m.is_active,
        "scheduled_start":     m.scheduled_start.isoformat() if m.scheduled_start else None,
        "estimated_end":       m.estimated_end.isoformat()   if m.estimated_end   else None,
        "show_countdown":      m.show_countdown,
        "auto_end":            m.auto_end,                   # ← new
        "message":             m.message,
        "seconds_until_start": seconds_until_start,
        "seconds_until_end":   seconds_until_end,
    }