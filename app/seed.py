"""Seed reference data.

    python -m app.seed                 # categories, badges, example sources (disabled)
    python -m app.seed --dev-users     # also create demo users (refused in production)
"""
from __future__ import annotations

import argparse
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.enums import BadgeCriterion, Role
from app.db.models import Badge, Category, TechnologySource, User
from app.db.session import new_session

CATEGORIES = ["Agentic AI", "Data Engineering", "Small Language Models", "Cloud & Infra"]

BADGES = [
    ("first-volunteer", "First Volunteer", "Joined your first technology topic.", BadgeCriterion.VOLUNTEER, 1),
    ("test-case-author", "Test Case Author", "Added 3 reusable test cases.", BadgeCriterion.TESTCASES, 3),
    ("artifact-contributor", "Artifact Contributor", "Had your first artifact approved.", BadgeCriterion.ARTIFACTS, 1),
    ("artifact-champion", "Artifact Champion", "Had 5 artifacts approved.", BadgeCriterion.ARTIFACTS, 5),
    ("presenter", "Presenter", "Completed a presentation stage.", BadgeCriterion.PRESENTATIONS, 1),
    ("topic-scout", "Topic Scout", "Had a suggested topic approved.", BadgeCriterion.TOPICS, 1),
]

# Public feeds, registered DISABLED: an admin decides which ones to switch on.
EXAMPLE_SOURCES = [
    ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml"),
    ("AWS Machine Learning Blog", "https://aws.amazon.com/blogs/machine-learning/feed/"),
    ("Databricks Blog", "https://www.databricks.com/feed"),
]

DEV_USERS = [("employee@neuleap.ai", "Dev Employee", Role.EMPLOYEE), ("reviewer@neuleap.ai", "Dev Reviewer", Role.ADMIN),
             ("admin@neuleap.ai", "Dev Admin", Role.ADMIN)]


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def seed_reference_data(db: Session, *, example_sources: bool = False) -> dict[str, int]:
    added = {"categories": 0, "badges": 0, "sources": 0}
    cats = {c.name for c in db.scalars(select(Category))}
    for name in CATEGORIES:
        if name not in cats:
            db.add(Category(name=name, slug=slugify(name)))
            added["categories"] += 1
    keys = {b.key for b in db.scalars(select(Badge))}
    for key, name, desc, crit, thr in BADGES:
        if key not in keys:
            db.add(Badge(key=key, name=name, description=desc, criterion=crit, threshold=thr))
            added["badges"] += 1
    urls = {s.url for s in db.scalars(select(TechnologySource))}
    for name, url in (EXAMPLE_SOURCES if example_sources else []):  # opt-in: sources are live as soon as they exist
        if url not in urls:
            db.add(TechnologySource(name=name, url=url))
            added["sources"] += 1
    db.commit()
    return added


def seed_dev_users(db: Session) -> int:
    if get_settings().is_production:
        raise SystemExit("Refusing to create development users when ENVIRONMENT=production")
    n = 0
    for email, name, role in DEV_USERS:
        if not db.scalar(select(User.id).where(User.email == email)):
            db.add(User(email=email, display_name=name, role=role))
            n += 1
    db.commit()
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dev-users", action="store_true", help="create demo users (never in production)")
    ap.add_argument("--example-sources", action="store_true", help="also add three example feed sources (they will be crawled)")
    args = ap.parse_args()
    db = new_session()
    try:
        print("seeded:", seed_reference_data(db, example_sources=args.example_sources))
        if args.dev_users:
            print("dev users created:", seed_dev_users(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
