from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DatabaseSession

from .activity import record, timestamp
from .models import Session, User
from .schemas import Login, Registration
from .security import (
    cookie_name, credentials_match, db_session, issue_session, password_slots, passwords, require_user,
    set_session_cookie,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def user_json(user: User) -> dict:
    return dict(id=user.id, full_name=user.full_name, email=user.email, student_id=user.student_id,
                role=user.role, department=user.department, academic_year=user.academic_year,
                created_at=timestamp(user.created_at))


def throttle(request: Request, db: DatabaseSession = Depends(db_session)):
    peer = request.client.host if request.client else "unknown"
    if not request.app.state.auth_limit.allow(peer):
        request.state.rate_limit_outcome = "denied"
        record(db, request, "authentication_rate_limited", outcome="denied")
        db.commit()
        raise HTTPException(429, "Too many attempts. Try again in a minute.", headers={"Retry-After": "60"})
    request.state.rate_limit_outcome = "allowed"


@router.post("/register", status_code=201, dependencies=[Depends(throttle)])
def register(payload: Registration, request: Request, response: Response, db: DatabaseSession = Depends(db_session)):
    with password_slots:
        password_hash = passwords.hash(payload.password)
    user = User(full_name=payload.full_name, email=payload.email.casefold(),
                student_id=payload.student_id, password_hash=password_hash)
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "This email or student ID is already registered")
    csrf = issue_session(request, response, db, user)
    request.state.user_id = user.id
    request.state.auth_outcome = "authenticated"
    record(db, request, "account_registered", user_id=user.id)
    db.commit()
    return {"user": user_json(user), "csrf_token": csrf}


@router.post("/login", dependencies=[Depends(throttle)])
def login(payload: Login, request: Request, response: Response, db: DatabaseSession = Depends(db_session)):
    user = db.scalar(select(User).where(User.email == payload.email.casefold()))
    with password_slots:
        verified = credentials_match(user, payload.password)
        if verified and passwords.check_needs_rehash(user.password_hash):
            user.password_hash = passwords.hash(payload.password)
    if not verified:
        request.state.auth_outcome = "denied"
        record(db, request, "login_failed", outcome="denied")
        db.commit()
        raise HTTPException(401, "Invalid email or password")

    # A successful sign-in replaces any session already presented by this browser.
    existing = request.cookies.get(cookie_name(request))
    if existing:
        from jwt import InvalidTokenError, decode
        try:
            claims = decode(existing, request.app.state.settings.jwt_secret.get_secret_value(),
                            algorithms=["HS256"], audience="northfield-portal",
                            options={"require": ["jti", "exp"]})
            db.execute(delete(Session).where(Session.id == claims["jti"]))
        except InvalidTokenError:
            pass

    csrf = issue_session(request, response, db, user)
    request.state.user_id = user.id
    request.state.auth_outcome = "authenticated"
    record(db, request, "login_succeeded", user_id=user.id)
    db.commit()
    return {"user": user_json(user), "csrf_token": csrf}


@router.get("/me")
def me(request: Request, user: User = Depends(require_user)):
    return {"user": user_json(user), "csrf_token": request.state.csrf}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(require_user),
           db: DatabaseSession = Depends(db_session)):
    db.execute(delete(Session).where(Session.id == request.state.session_id))
    record(db, request, "logout", user_id=user.id)
    db.commit()
    set_session_cookie(request, response, "", max_age=0)
