import argparse
from getpass import getpass

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from .audit import audit
from .auth import PERMISSIONS, password_hasher
from .config import settings
from .database import make_engine
from .models import Role, User, project_memberships, projects
from .repositories import find_user


def main():
    parser = argparse.ArgumentParser(description="Provision a local Timmy account.")
    parser.add_argument("username")
    parser.add_argument("--role", choices=sorted(PERMISSIONS), required=True)
    parser.add_argument("--demo-projects", action="store_true")
    args = parser.parse_args()
    if not args.username.strip() or len(args.username) > 80:
        parser.error("Use a nonempty username of at most 80 characters")
    config = settings()
    if args.demo_projects and not config.demo_mode:
        parser.error("Enable TIMMY_DEMO_MODE before adding demo projects")
    password = getpass("Password: ")
    if not 12 <= len(password) <= 1024 or password != getpass("Confirm password: "):
        parser.error("Passwords must match and contain 12–1024 characters")

    engine = make_engine(config.database_url)
    with Session(engine) as db, db.begin():
        if find_user(db, args.username):
            parser.error("Username already exists")
        role = db.scalar(select(Role).where(Role.name == args.role))
        if role is None:
            role = Role(name=args.role)
            db.add(role)
            db.flush()
        user = User(username=args.username, password_hash=password_hasher.hash(password), role_id=role.id)
        db.add(user)
        db.flush()
        if args.demo_projects:
            for number in range(1, 4):
                name = f"Demo — Project {number}"
                project_id = db.scalar(select(projects.c.id).where(projects.c.name == name))
                if project_id is None:
                    project_id = db.execute(insert(projects).values(name=name)).inserted_primary_key[0]
                db.execute(insert(project_memberships).values(project_id=project_id, user_id=user.id))
        audit(db, "local_account_created")
    print("Account created.")


if __name__ == "__main__":
    main()
