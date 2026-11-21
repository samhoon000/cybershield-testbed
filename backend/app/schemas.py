from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=8000)]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
StudentCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9-]{3,32}$")]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Registration(Login):
    full_name: Name
    student_id: StudentCode
    password: Password
    confirm_password: Password

    @model_validator(mode="after")
    def validate_confirmation(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords must match")
        return self


class CourseInput(Input):
    title: Title
    description: Description
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]
    instructor: Name
    duration: int = Field(ge=1, le=104)
    status: Literal["open", "closed"]


class ProgressInput(Input):
    progress: int = Field(ge=0, le=100)


class AssignmentInput(Input):
    course_id: int = Field(gt=0)
    title: Title
    description: Description
    deadline: datetime

    @field_validator("deadline")
    @classmethod
    def validate_deadline(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError("Include the assignment deadline's time zone")
        return value.astimezone(UTC).replace(tzinfo=None)


class SubmissionInput(Input):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class ProfileInput(Input):
    full_name: Name
    department: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
    academic_year: int | None = Field(ge=1, le=8)
