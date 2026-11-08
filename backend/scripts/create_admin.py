from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User


def main():
    email = input("Admin email: ").strip().lower()
    full_name = input("Full name: ").strip()

    if (
        email.count("@") != 1
        or not all(email.split("@"))
        or len(email) > 255
        or any(char.isspace() for char in email)
    ):
        print("Invalid email.")
        return

    if not full_name or len(full_name) > 150:
        print("Full name must contain 1-150 characters.")
        return

    password = getpass("Password (at least 12 characters): ")
    confirmation = getpass("Confirm password: ")

    if len(password) < 12:
        print("Password must contain at least 12 characters.")
        return

    if password != confirmation:
        print("Passwords do not match.")
        return

    with SessionLocal() as session:
        existing = session.scalar(
            select(User).where(User.email == email)
        )

        if existing is not None:
            print("Email already exists. No changes made.")
            return

        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )

        session.add(user)
        session.commit()
        session.refresh(user)

        print(f"Admin created: id={user.id}, email={user.email}")


if __name__ == "__main__":
    main()