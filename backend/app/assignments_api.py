from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, insert, literal, select
from sqlalchemy.orm import Session, joinedload

from .activity import record, timestamp
from .courses_api import find_course
from .models import Assignment, Enrollment, Submission, User, now
from .schemas import AssignmentInput, SubmissionInput
from .security import admin_only, db_session, require_user, student_only

router = APIRouter(prefix="/assignments", tags=["Assignments"])


def permitted_assignments(user: User):
    statement = select(Assignment).options(joinedload(Assignment.course))
    if user.role == "student":
        statement = statement.join(Enrollment, Enrollment.course_id == Assignment.course_id).where(
            Enrollment.user_id == user.id)
    return statement


def submissions_for(user: User, assignment_id: int):
    statement = select(Submission).where(Submission.assignment_id == assignment_id)
    if user.role == "student":
        statement = statement.where(Submission.student_id == user.id)
    return statement.order_by(Submission.submitted_at.desc(), Submission.id.desc())


def find_assignment(assignment_id: int, user: User, request: Request, db: Session) -> Assignment:
    assignment = db.scalar(permitted_assignments(user).where(Assignment.id == assignment_id))
    if assignment is None:
        if user.role == "student":
            record(db, request, "authorization_failed", user_id=user.id, resource_type="assignment",
                   resource_id=assignment_id, outcome="denied")
            db.commit()
        raise HTTPException(404, "Assignment not found")
    return assignment


def assignment_json(assignment: Assignment, count: int) -> dict:
    return dict(id=assignment.id, course_id=assignment.course_id, course_title=assignment.course.title,
                title=assignment.title, description=assignment.description, deadline=timestamp(assignment.deadline),
                submission_count=count, overdue=assignment.deadline <= now())


def submission_json(submission: Submission, include_student: bool = False) -> dict:
    data = dict(id=submission.id, content=submission.content, submitted_at=timestamp(submission.submitted_at),
                status=submission.status)
    if include_student:
        data.update(student_id=submission.student.student_id, student_name=submission.student.full_name)
    return data


def assignment_rows(db: Session, user: User, upcoming=False, limit: int | None = None) -> list[dict]:
    counts = select(func.count(Submission.id)).where(Submission.assignment_id == Assignment.id)
    if user.role == "student":
        counts = counts.where(Submission.student_id == user.id)
    count = counts.correlate(Assignment).scalar_subquery()
    statement = permitted_assignments(user).add_columns(count).order_by(Assignment.deadline, Assignment.id)
    if upcoming:
        statement = statement.where(Assignment.deadline > now(), count == 0)
    return [assignment_json(assignment, total) for assignment, total in db.execute(statement.limit(limit))]


@router.get("")
def list_assignments(user: User = Depends(require_user), db: Session = Depends(db_session)):
    return assignment_rows(db, user)


@router.post("", dependencies=[Depends(admin_only)], status_code=201)
def create(payload: AssignmentInput, db: Session = Depends(db_session)):
    if payload.deadline <= now():
        raise HTTPException(422, "Deadline must be in the future")
    course = find_course(payload.course_id, db)
    assignment = Assignment(**payload.model_dump(), course=course)
    db.add(assignment)
    db.commit()
    return assignment_json(assignment, 0)


@router.get("/{assignment_id}")
def detail(assignment_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(db_session)):
    assignment = find_assignment(assignment_id, user, request, db)
    total = db.scalar(select(func.count()).select_from(submissions_for(user, assignment_id).order_by(None).subquery()))
    return assignment_json(assignment, total)


@router.put("/{assignment_id}")
def edit(assignment_id: int, payload: AssignmentInput, request: Request, user: User = Depends(admin_only),
         db: Session = Depends(db_session)):
    assignment = find_assignment(assignment_id, user, request, db)
    if payload.course_id != assignment.course_id:
        raise HTTPException(409, "An assignment must stay in its original course")
    if payload.deadline != assignment.deadline and payload.deadline <= now():
        raise HTTPException(422, "Choose a future deadline to reschedule this assignment")
    for key, value in payload.model_dump(exclude={"course_id"}).items():
        setattr(assignment, key, value)
    total = db.scalar(select(func.count(Submission.id)).where(Submission.assignment_id == assignment.id))
    db.commit()
    return assignment_json(assignment, total)


@router.post("/{assignment_id}/submit", status_code=201)
def submit(assignment_id: int, payload: SubmissionInput, request: Request, user: User = Depends(student_only),
           db: Session = Depends(db_session)):
    source = (select(Assignment.id, literal(user.id), literal(payload.content), func.datetime("now"),
                     literal("submitted"))
              .join(Enrollment, Enrollment.course_id == Assignment.course_id)
              .where(Assignment.id == assignment_id, Enrollment.user_id == user.id,
                     func.julianday(Assignment.deadline) > func.julianday("now")))
    statement = (insert(Submission)
                 .from_select(["assignment_id", "student_id", "content", "submitted_at", "status"], source)
                 .returning(Submission))
    submission = db.scalar(statement)
    if submission is None:
        find_assignment(assignment_id, user, request, db)
        raise HTTPException(409, "The submission deadline has passed")
    record(db, request, "assignment_submitted", user_id=user.id, resource_type="assignment", resource_id=assignment_id)
    db.commit()
    return submission_json(submission)


@router.get("/{assignment_id}/submissions")
def history(assignment_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(db_session),
            offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    find_assignment(assignment_id, user, request, db)
    statement = submissions_for(user, assignment_id)
    return [submission_json(submission, user.role == "admin") for submission in
            db.scalars(statement.options(joinedload(Submission.student)).offset(offset).limit(limit))]
