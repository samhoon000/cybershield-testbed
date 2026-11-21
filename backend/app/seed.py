from random import Random
from datetime import timedelta
from secrets import token_urlsafe
from uuid import uuid4

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select

from .config import Settings
from .db import make_engine, make_sessions
from .models import Activity, Assignment, Course, Enrollment, Submission, User, now
from .security import passwords

COURSES = [
    ("Applied Data Analytics", "Data Science", "Dr. Mina Patel", 10,
     "Turn messy datasets into clear findings with exploratory analysis, visualization, and reproducible notebooks."),
    ("Web Application Development", "Computing", "Professor Elena Cruz", 12,
     "Build accessible web applications and connect front-end experiences to robust APIs."),
    ("Human-Centered Design", "Design", "Professor Jonah Miles", 8,
     "Use interviews, journey maps, and usability testing to design services around real needs."),
    ("Algorithms and Complexity", "Computing", "Dr. Priya Iyer", 12,
     "Analyze core data structures and compare algorithmic approaches to search, sorting, and optimization."),
    ("Database Systems", "Computing", "Professor Nadia Chen", 10,
     "Design relational models, reason about transactions, and build dependable data-backed applications."),
    ("Environmental Science", "Natural Sciences", "Dr. Leo Brooks", 10,
     "Study ecosystems, energy flows, and the trade-offs behind community sustainability decisions."),
    ("Visual Communication", "Design", "Professor Sofia Warren", 8,
     "Explore composition, typography, and hierarchy through a series of editorial design exercises."),
    ("Statistics for Research", "Data Science", "Dr. Nikhil Rao", 11,
     "Evaluate sampling, confidence intervals, and hypothesis tests using applied research examples."),
    ("Technical Writing", "Humanities", "Dr. Isla Reed", 7,
     "Write clear technical explanations, documentation, and evidence-led proposals for different audiences."),
    ("Cognitive Psychology", "Social Sciences", "Dr. Amara Okafor", 10,
     "Investigate attention, working memory, and how people make decisions under uncertainty."),
    ("Project Management", "Business", "Professor Rafael Silva", 9,
     "Scope work, forecast delivery, and communicate decisions with practical project planning methods."),
    ("Introduction to Economics", "Business", "Dr. Hannah Talbot", 12,
     "Apply economic models to individual decisions, market outcomes, and public policy."),
]
STUDENTS = [
    "Jordan Lee", "Maya Bennett", "Arjun Shah", "Camila Ruiz", "Noah Patel", "Zoe Carter",
    "Ibrahim Malik", "Elise Tan", "Daniel Park", "Avery Morgan", "Leila Ahmed", "Mateo Flores",
    "Sana Kapoor", "Samuel Green", "Nora Williams", "Lucas Ferreira", "Mei Lin", "Aisha Brown",
]


def seed_demo(settings: Settings, sessions) -> bool:
    production = settings.app_env == "production"
    if production and not settings.seed_demo_data:
        raise SystemExit("Set SEED_DEMO_DATA=true to seed a public demo.")
    email_validator = TypeAdapter(EmailStr)
    try:
        admin_email = email_validator.validate_python(settings.demo_admin_email).casefold()
        first_student_email = email_validator.validate_python(settings.demo_student_email).casefold()
    except ValueError:
        raise SystemExit("Set valid DEMO_ADMIN_EMAIL and DEMO_STUDENT_EMAIL values.") from None
    admin_password = settings.demo_admin_password.get_secret_value()
    student_password = settings.demo_student_password.get_secret_value()
    minimum_length = 24 if production else 12
    if not all(minimum_length <= len(value) <= 128 for value in (admin_password, student_password)):
        raise SystemExit(f"Set independent random demo passwords of {minimum_length} to 128 characters.")
    if admin_email == first_student_email or admin_password == student_password:
        raise SystemExit("Use different administrator and student credentials.")

    random = Random(72)
    current = now()
    with sessions.begin() as db:
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        existing_admin = db.scalar(select(User).where(User.student_id == "NF-DEMO-ADMIN"))
        if existing_admin:
            if existing_admin.role != "admin" or existing_admin.email != admin_email:
                raise SystemExit("The demo administrator account conflicts with the configured demo.")
            return False
        admin = User(full_name="Morgan Ellis", student_id="NF-DEMO-ADMIN", email=admin_email,
                     role="admin", password_hash=passwords.hash(admin_password))
        students = [User(full_name=name, student_id=f"NF-{1024 + index}",
                         email=first_student_email if index == 0 else f"student{index + 1:02}@northfield.example.com",
                         department=COURSES[index % len(COURSES)][1], academic_year=index % 4 + 1,
                         created_at=current - timedelta(days=66 + index),
                         password_hash=passwords.hash(token_urlsafe(32) if production and index else student_password))
                    for index, name in enumerate(STUDENTS)]
        courses = [Course(title=title, category=category, instructor=instructor, duration=duration,
                          description=description, status="closed" if index == 10 else "open")
                   for index, (title, category, instructor, duration, description) in enumerate(COURSES)]
        db.add_all([admin, *students, *courses])
        db.flush()
        assignments = {}
        for index, course in enumerate(courses):
            pair = [
                Assignment(course=course, title="Foundations reflection",
                           description=f"Summarize two concepts from {course.title} and explain where they apply.",
                           deadline=current - timedelta(days=6)),
                Assignment(course=course, title="Applied case study",
                           description=f"Choose a case from {course.title}. Explain your approach, cite your evidence, "
                                       "and discuss one limitation in 300–500 words.",
                           deadline=current + timedelta(days=index + 3)),
            ]
            assignments[course.id] = pair
            db.add_all(pair)
        db.flush()

        for index, student in enumerate(students):
            chosen = courses[:4] if index == 0 else random.sample(courses, 4)
            for position, course in enumerate(chosen):
                progress = [75, 48, 100, 24][position] if index == 0 else random.choice([12, 30, 54, 72, 100])
                enrolled_at = current - timedelta(days=43 - position)
                db.add(Enrollment(user=student, course=course, progress=progress, enrolled_at=enrolled_at,
                                  last_accessed_at=current - timedelta(days=position + 1),
                                  completed_at=current - timedelta(days=3) if progress == 100 else None))
                db.add(Activity(user_id=student.id, event_type="course_enrolled", outcome="success",
                                resource_type="course", resource_id=course.id, request_id=str(uuid4()),
                                created_at=enrolled_at))
                if position < 3:
                    first = assignments[course.id][0]
                    submitted_at = current - timedelta(days=8)
                    db.add(Submission(student=student, assignment=first,
                                      content=f"My reflection on {course.title} compares the method used in class "
                                              "with an example drawn from a campus project.",
                                      submitted_at=submitted_at))
                    db.add(Activity(user_id=student.id, event_type="assignment_submitted", outcome="success",
                                    resource_type="assignment", resource_id=first.id, request_id=str(uuid4()),
                                    created_at=submitted_at))

    return True


def main():
    settings = Settings()
    engine = make_engine(settings.sqlite_path)
    try:
        seeded = seed_demo(settings, make_sessions(engine))
    finally:
        engine.dispose()
    print("Demo data initialized." if seeded else "Demo records already exist.")


if __name__ == "__main__":
    main()
