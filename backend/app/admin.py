import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter
from sqlalchemy.exc import IntegrityError

from .config import Settings
from .db import make_engine, make_sessions
from .models import User
from .schemas import Name, Password, StudentCode
from .security import passwords


def main():
    parser = argparse.ArgumentParser(description="Provision an administrator on a migrated portal database.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--account-id", required=True)
    arguments = parser.parse_args()
    try:
        email = TypeAdapter(EmailStr).validate_python(arguments.email).casefold()
        name = TypeAdapter(Name).validate_python(arguments.name)
        account_id = TypeAdapter(StudentCode).validate_python(arguments.account_id)
        password = TypeAdapter(Password).validate_python(getpass("New administrator password: "))
    except ValueError:
        raise SystemExit("Enter a valid email, name, account ID, and a 12–128 character password.") from None
    if password != getpass("Confirm administrator password: "):
        raise SystemExit("Passwords must match.")
    sessions = make_sessions(make_engine(Settings().sqlite_path))
    try:
        with sessions.begin() as db:
            db.add(User(email=email, full_name=name, student_id=account_id, role="admin",
                        password_hash=passwords.hash(password)))
    except IntegrityError:
        raise SystemExit("The email or account ID already exists.") from None
    print("Administrator created.")


if __name__ == "__main__":
    main()
