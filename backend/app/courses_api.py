from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from .activity import record, timestamp
from .models import Course, Enrollment, User, now
from .schemas import CourseInput, ProgressInput
from .security import admin_only, db_session, require_user, student_only

router = APIRouter(prefix="/courses", tags=["Courses"])

enrollment_count = (
    select(func.count(Enrollment.id)).where(Enrollment.course_id == Course.id).correlate(Course).scalar_subquery()
)


def course_json(course: Course, count: int, enrollment: Enrollment | None = None) -> dict:
    return dict(id=course.id, title=course.title, description=course.description, category=course.category,
                instructor=course.instructor, duration=course.duration, status=course.status, enrollment_count=count,
                progress=enrollment.progress if enrollment else None,
                completed_at=timestamp(enrollment.completed_at) if enrollment else None)


def enrolled_courses(db: Session, user_id: int, limit: int | None = None) -> list[dict]:
    statement = (select(Course, enrollment_count, Enrollment).join(Enrollment)
                 .where(Enrollment.user_id == user_id)
                 .order_by(Enrollment.last_accessed_at.desc(), Course.id.desc()).limit(limit))
    return [course_json(course, count, enrollment) for course, count, enrollment in db.execute(statement)]


def find_course(course_id: int, db: Session) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    return course


@router.get("")
def directory(user: User = Depends(require_user), db: Session = Depends(db_session),
              search: str = Query("", max_length=120), category: str = Query("", max_length=60),
              sort: Literal["title", "newest", "popular"] = "title",
              page: int = Query(1, ge=1, le=100000), page_size: int = Query(9, ge=1, le=50)):
    filters = []
    if search.strip():
        filters.append(Course.title.icontains(search.strip(), autoescape=True))
    if category:
        filters.append(Course.category == category)
    order = {"title": func.lower(Course.title), "newest": Course.created_at.desc(), "popular": enrollment_count.desc()}
    statement = (select(Course, enrollment_count, Enrollment)
                 .outerjoin(Enrollment, (Enrollment.course_id == Course.id) & (Enrollment.user_id == user.id))
                 .where(*filters).order_by(order[sort], Course.id).offset((page - 1) * page_size).limit(page_size))
    return dict(items=[course_json(course, count, enrollment) for course, count, enrollment in db.execute(statement)],
                total=db.scalar(select(func.count(Course.id)).where(*filters)), page=page, page_size=page_size,
                categories=list(db.scalars(select(Course.category).distinct().order_by(Course.category))))


@router.get("/enrolled")
def enrolled(user: User = Depends(student_only), db: Session = Depends(db_session)):
    return enrolled_courses(db, user.id)


@router.post("", status_code=201, dependencies=[Depends(admin_only)])
def create(payload: CourseInput, db: Session = Depends(db_session)):
    course = Course(**payload.model_dump())
    db.add(course)
    db.commit()
    return course_json(course, 0)


@router.get("/{course_id}")
def detail(course_id: int, user: User = Depends(require_user), db: Session = Depends(db_session)):
    row = db.execute(select(Course, enrollment_count, Enrollment)
                     .outerjoin(Enrollment, (Enrollment.course_id == Course.id) & (Enrollment.user_id == user.id))
                     .where(Course.id == course_id)).one_or_none()
    if row is None:
        raise HTTPException(404, "Course not found")
    return course_json(*row)


@router.put("/{course_id}", dependencies=[Depends(admin_only)])
def edit(course_id: int, payload: CourseInput, db: Session = Depends(db_session)):
    course = find_course(course_id, db)
    for key, value in payload.model_dump().items():
        setattr(course, key, value)
    db.commit()
    return course_json(course, db.scalar(select(enrollment_count).select_from(Course).where(Course.id == course_id)))


@router.delete("/{course_id}", status_code=204, dependencies=[Depends(admin_only)])
def remove(course_id: int, db: Session = Depends(db_session)):
    db.delete(find_course(course_id, db))
    db.commit()


@router.post("/{course_id}/enroll", status_code=201)
def enroll(course_id: int, request: Request, user: User = Depends(student_only), db: Session = Depends(db_session)):
    source = select(literal(user.id), Course.id).where(Course.id == course_id, Course.status == "open")
    statement = (insert(Enrollment).from_select(["user_id", "course_id"], source)
                 .on_conflict_do_nothing(index_elements=["user_id", "course_id"]).returning(Enrollment.progress))
    progress_value = db.scalar(statement)
    if progress_value is None:
        if find_course(course_id, db).status != "open":
            raise HTTPException(409, "This course is closed for enrollment")
        raise HTTPException(409, "You are already enrolled in this course")
    record(db, request, "course_enrolled", user_id=user.id, resource_type="course", resource_id=course_id)
    db.commit()
    return {"progress": progress_value}


@router.post("/{course_id}/access", status_code=204)
def access(course_id: int, user: User = Depends(student_only), db: Session = Depends(db_session)):
    result = db.execute(update(Enrollment).where(Enrollment.user_id == user.id, Enrollment.course_id == course_id)
                        .values(last_accessed_at=now()))
    if not result.rowcount:
        raise HTTPException(404, "Enrollment not found")
    db.commit()


@router.put("/{course_id}/progress")
def progress(course_id: int, payload: ProgressInput, user: User = Depends(student_only),
             db: Session = Depends(db_session)):
    enrollment = db.scalar(select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.course_id == course_id))
    if enrollment is None:
        raise HTTPException(404, "Enrollment not found")
    enrollment.progress = payload.progress
    enrollment.completed_at = (enrollment.completed_at or now()) if payload.progress == 100 else None
    enrollment.last_accessed_at = now()
    db.commit()
    return {"progress": enrollment.progress, "completed_at": timestamp(enrollment.completed_at)}
