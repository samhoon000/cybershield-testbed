from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .activity import activity_json, record
from .assignments_api import assignment_rows
from .auth_api import user_json
from .courses_api import enrolled_courses
from .models import Activity, Assignment, Course, Enrollment, Submission, User, now
from .schemas import ProfileInput
from .security import admin_only, db_session, require_user

router = APIRouter(tags=["Portal"])


def activities(db: Session, user: User, limit: int, offset: int = 0, event_type: str = ""):
    statement = select(Activity)
    if user.role == "student":
        statement = statement.where(Activity.user_id == user.id)
    if event_type:
        statement = statement.where(Activity.event_type == event_type)
    return [activity_json(event) for event in db.scalars(
        statement.order_by(Activity.created_at.desc(), Activity.id.desc()).offset(offset).limit(limit))]


@router.get("/dashboard/stats")
def dashboard(user: User = Depends(require_user), db: Session = Depends(db_session)):
    if user.role == "admin":
        return dict(role="admin", students=db.scalar(select(func.count(User.id)).where(User.role == "student")),
                    courses=db.scalar(select(func.count(Course.id))), assignments=db.scalar(select(func.count(Assignment.id))),
                    submissions=db.scalar(select(func.count(Submission.id))), activity=activities(db, user, 5))

    enrolled, completed, average = db.execute(
        select(func.count(), func.count(Enrollment.completed_at), func.avg(Enrollment.progress))
        .where(Enrollment.user_id == user.id)
    ).one()
    submitted = select(Submission.id).where(Submission.assignment_id == Assignment.id,
                                            Submission.student_id == user.id).exists()
    assignment_query = (select(func.count(Assignment.id)).join(Enrollment, Enrollment.course_id == Assignment.course_id)
                        .where(Enrollment.user_id == user.id))
    sent = db.scalar(assignment_query.where(submitted))
    pending = db.scalar(assignment_query.where(~submitted, Assignment.deadline > now()))
    overdue = db.scalar(assignment_query.where(~submitted, Assignment.deadline <= now()))
    return dict(role="student", enrolled=enrolled, completed=completed, pending=pending, progress=round(average or 0),
                submission_stats=[{"name": "Submitted", "value": sent}, {"name": "Pending", "value": pending},
                                  {"name": "Overdue", "value": overdue}],
                recent_courses=enrolled_courses(db, user.id, limit=4),
                upcoming=assignment_rows(db, user, upcoming=True, limit=4), activity=activities(db, user, 5))


@router.get("/dashboard/activity")
def dashboard_activity(user: User = Depends(require_user), db: Session = Depends(db_session)):
    return activities(db, user, 5)


@router.get("/students")
def students(_: User = Depends(admin_only), db: Session = Depends(db_session), offset: int = Query(0, ge=0),
             limit: int = Query(25, ge=1, le=100)):
    statement = select(User).where(User.role == "student").order_by(User.full_name, User.id)
    return [user_json(user) for user in db.scalars(statement.offset(offset).limit(limit))]


@router.get("/students/me")
def profile(user: User = Depends(require_user), db: Session = Depends(db_session)):
    return {**user_json(user), "enrolled_courses": enrolled_courses(db, user.id)}


@router.put("/students/me")
def update_profile(payload: ProfileInput, request: Request, user: User = Depends(require_user),
                   db: Session = Depends(db_session)):
    for field, value in payload.model_dump().items():
        setattr(user, field, value)
    record(db, request, "profile_updated", user_id=user.id, resource_type="profile", resource_id=user.id)
    db.commit()
    return {**user_json(user), "enrolled_courses": enrolled_courses(db, user.id)}


@router.get("/activity")
def list_activity(user: User = Depends(require_user), db: Session = Depends(db_session),
                  offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100),
                  event_type: str = Query("", max_length=48)):
    return activities(db, user, limit, offset, event_type)
