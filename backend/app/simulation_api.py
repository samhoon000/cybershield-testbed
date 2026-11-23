"""CyberShield Persistent Security Incident Simulation Service.

Provides authenticated activation, session state tracking, presentation unlock,
and emergency recovery endpoints for Sentinel AI integration.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DatabaseSession

from .activity import record, timestamp
from .models import SimulationSession, now
from .security import db_session

router = APIRouter(prefix="/simulation", tags=["Security Incident Simulation"])


class ActivatePayload(BaseModel):
    notes: Optional[str] = "Sentinel AI College Project Presentation"
    ttl_minutes: Optional[int] = Field(default=30, ge=1, le=1440)


class UnlockPayload(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)


class TerminatePayload(BaseModel):
    session_id: Optional[str] = None


def verify_sentinel_key(
    request: Request,
    x_cybershield_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> bool:
    """Verifies that the incoming request originates from authorized Sentinel AI controller."""
    expected = request.app.state.settings.sentinel_allowed_api_key.get_secret_value()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SENTINEL_ALLOWED_API_KEY is not configured on CyberShield",
        )

    provided = x_cybershield_key
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()

    if not provided or not secrets.compare_digest(provided.strip(), expected.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing CyberShield API key",
        )
    return True


def _clean_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _get_base_url(request: Request) -> str:
    settings = request.app.state.settings
    if settings.frontend_base_url:
        return settings.frontend_base_url.rstrip("/")

    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")

    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        return f"{parts.scheme}://{parts.netloc}".rstrip("/")

    host = request.headers.get("host", "127.0.0.1:8000")
    scheme = "https" if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" else "http"
    return f"{scheme}://{host}"


@router.get("/ping")
def simulation_ping(request: Request):
    """Connectivity and status probe for Sentinel AI Attack Lab."""
    settings = request.app.state.settings
    return {
        "status": "online",
        "target": "CyberShield",
        "service": "CyberShield Testbed",
        "simulation_enabled": settings.screen_lock_simulation_enabled,
        "default_ttl_minutes": settings.screen_lock_session_ttl,
        "timestamp": timestamp(now()),
    }


@router.post("/activate")
def activate_simulation(
    payload: ActivatePayload,
    request: Request,
    response: Response,
    _: bool = Depends(verify_sentinel_key),
    db: DatabaseSession = Depends(db_session),
):
    """Activated exclusively by Sentinel AI controller via authenticated server-to-server request."""
    settings = request.app.state.settings
    if not settings.screen_lock_simulation_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Screen lock simulation is disabled in CyberShield settings",
        )

    # Generate incident identifier and cryptographically secure session reference
    incident_id = f"INC-{secrets.token_hex(4).upper()}-{secrets.token_hex(2).upper()}"
    session_id = f"sim_{secrets.token_urlsafe(24)}"
    ttl = payload.ttl_minutes or settings.screen_lock_session_ttl
    start_time = now()
    expire_time = start_time + timedelta(minutes=ttl)
    client_ip = request.client.host if request.client else "unknown"

    sim_session = SimulationSession(
        id=session_id,
        incident_id=incident_id,
        status="active",
        target_app="CyberShield",
        created_at=start_time,
        expires_at=expire_time,
        client_ip=client_ip,
        notes=payload.notes,
    )
    db.add(sim_session)
    record(db, request, "security_incident_simulation_activated", outcome="activated")
    db.commit()

    base_url = _get_base_url(request)
    launch_url = f"{base_url}/?sim_session={session_id}"

    # Also set a cross-origin / same-site readable cookie so current browser tab is immediately aware
    response.set_cookie(
        key="cybershield_sim_session",
        value=session_id,
        max_age=ttl * 60,
        httponly=False,  # Frontend JavaScript needs to read session identifier
        samesite="lax",
        secure=request.url.scheme == "https",
    )

    return {
        "status": "active",
        "incident_id": incident_id,
        "session_id": session_id,
        "target_app": "CyberShield",
        "created_at": _clean_iso(start_time),
        "expires_at": _clean_iso(expire_time),
        "launch_url": launch_url,
        "ttl_minutes": ttl,
        "notes": payload.notes,
    }


@router.get("/session/{session_id}")
def get_simulation_session(session_id: str, db: DatabaseSession = Depends(db_session)):
    """Fetches session state. Scoped to the individual session ID for frontend polling/persistence."""
    sim_session = db.scalar(select(SimulationSession).where(SimulationSession.id == session_id))
    if not sim_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulation session not found")

    current_time = now()
    if sim_session.status == "active" and sim_session.expires_at < current_time:
        sim_session.status = "expired"
        db.commit()

    return {
        "session_id": sim_session.id,
        "incident_id": sim_session.incident_id,
        "status": sim_session.status,
        "target_app": sim_session.target_app,
        "created_at": _clean_iso(sim_session.created_at),
        "expires_at": _clean_iso(sim_session.expires_at),
        "unlocked_at": _clean_iso(sim_session.unlocked_at),
        "terminated_at": _clean_iso(sim_session.terminated_at),
        "is_active": sim_session.status == "active",
    }


@router.get("/active")
def get_latest_active_session(db: DatabaseSession = Depends(db_session)):
    """Allows browser to check if an active simulation session is in progress."""
    current_time = now()
    sim_session = db.scalar(
        select(SimulationSession)
        .where(SimulationSession.status == "active", SimulationSession.expires_at > current_time)
        .order_by(SimulationSession.created_at.desc())
    )
    if not sim_session:
        return {"active": False, "session": None}

    return {
        "active": True,
        "session": {
            "session_id": sim_session.id,
            "incident_id": sim_session.incident_id,
            "status": sim_session.status,
            "target_app": sim_session.target_app,
            "created_at": _clean_iso(sim_session.created_at),
            "expires_at": _clean_iso(sim_session.expires_at),
        },
    }


@router.post("/unlock")
def unlock_simulation(
    payload: UnlockPayload,
    request: Request,
    response: Response,
    db: DatabaseSession = Depends(db_session),
):
    """Triggered by pressing the '0' keyboard key on CyberShield's incident screen."""
    sim_session = db.scalar(select(SimulationSession).where(SimulationSession.id == payload.session_id))
    if not sim_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Simulation session not found")

    current_time = now()
    if sim_session.status == "unlocked":
        # Already unlocked; idempotent success
        response.delete_cookie("cybershield_sim_session")
        return {
            "status": "unlocked",
            "incident_id": sim_session.incident_id,
            "message": "Session is already unlocked",
            "unlocked_at": _clean_iso(sim_session.unlocked_at),
        }

    if sim_session.expires_at < current_time:
        sim_session.status = "expired"
        db.commit()
        response.delete_cookie("cybershield_sim_session")
        return {
            "status": "expired",
            "incident_id": sim_session.incident_id,
            "message": "Simulation session has expired",
        }

    sim_session.status = "unlocked"
    sim_session.unlocked_at = current_time
    record(db, request, "security_incident_simulation_unlocked", outcome="unlocked")
    db.commit()

    # Clear simulation cookie
    response.delete_cookie("cybershield_sim_session")

    return {
        "status": "unlocked",
        "incident_id": sim_session.incident_id,
        "session_id": sim_session.id,
        "message": "Security incident simulation unlocked successfully via presentation key '0'",
        "unlocked_at": _clean_iso(current_time),
    }


@router.post("/terminate")
def terminate_simulation(
    payload: TerminatePayload,
    request: Request,
    response: Response,
    _: bool = Depends(verify_sentinel_key),
    db: DatabaseSession = Depends(db_session),
):
    """Emergency administrator recovery control initiated from Sentinel AI."""
    current_time = now()
    if payload.session_id:
        sim_session = db.scalar(select(SimulationSession).where(SimulationSession.id == payload.session_id))
        if not sim_session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        sim_session.status = "terminated"
        sim_session.terminated_at = current_time
    else:
        # Terminate any active sessions
        db.execute(
            update(SimulationSession)
            .where(SimulationSession.status == "active")
            .values(status="terminated", terminated_at=current_time)
        )

    record(db, request, "security_incident_simulation_terminated", outcome="terminated")
    db.commit()
    response.delete_cookie("cybershield_sim_session")

    return {
        "status": "terminated",
        "message": "Simulation session terminated by authorized administrator",
        "terminated_at": _clean_iso(current_time),
    }
