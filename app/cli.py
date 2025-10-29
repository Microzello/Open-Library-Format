"""CLI commands for admin tasks."""
import argparse
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth import AuthManager
from app.db.registry_db import RegistryDB
import os


def create_user_command(args):
    """Create a new user."""
    # Get secret from env
    secret = os.getenv("APP_SECRET", "change_me")
    auth = AuthManager(secret)
    
    # Hash password
    password_hash = auth.hash_password(args.password)
    
    # Create in registry
    registry = RegistryDB()
    user_id = registry.create_user(
        username=args.username,
        password_hash=password_hash,
        role="admin" if args.admin else "user"
    )
    
    print(f"User created: {args.username} (ID: {user_id})")
    
    # Mark bootstrap as done if this is first user
    bootstrap_sentinel = Path("var/bootstrap_done")
    if not bootstrap_sentinel.exists():
        bootstrap_sentinel.parent.mkdir(parents=True, exist_ok=True)
        bootstrap_sentinel.touch()
        print("Bootstrap marked as complete.")


def main():
    parser = argparse.ArgumentParser(description="Library Manager CLI")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # create-user command
    user_parser = subparsers.add_parser("create-user", help="Create a new user")
    user_parser.add_argument("username", help="Username")
    user_parser.add_argument("password", help="Password")
    user_parser.add_argument("--admin", action="store_true", help="Make user an admin")
    
    args = parser.parse_args()
    
    if args.command == "create-user":
        create_user_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

