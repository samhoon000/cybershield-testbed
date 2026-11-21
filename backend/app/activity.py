from datetime import UTC

from fastapi import Request
from sqlalchemy.orm import Session

from .models import Activity


def record(db: Session, request: Request, event_type: str, *, user_id: int | None = None,
           resource_type: str | None = None, resource_id: int | None = None,
           outcome: str = "success") -> None:
    db.add(Activity(
        event_type=event_type, user_id=user_id, resource_type=resource_type,
        resource_id=resource_id, outcome=outcome, request_id=request.state.request_id,
    ))


def timestamp(value):
    return value.replace(tzinfo=UTC).isoformat() if value else None


def activity_json(event: Activity) -> dict:
    return dict(id=event.id, user_id=event.user_id, event_type=event.event_type,
                resource_type=event.resource_type, resource_id=event.resource_id,
                outcome=event.outcome, request_id=event.request_id, created_at=timestamp(event.created_at))
