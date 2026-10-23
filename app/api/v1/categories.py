import re
import uuid

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, AdminUser, CurrentUser
from app.core.errors import Conflict, NotFound
from app.db.models import Category
from app.schemas.topics import CategoryIn, CategoryOut, CategoryPatch
from app.services.audit import audit

router = APIRouter(prefix="/categories", tags=["categories"])


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:120] or "category"


@router.get("", response_model=list[CategoryOut])
def list_categories(db: DB, _: CurrentUser, include_retired: bool = False):
    stmt = select(Category).order_by(Category.name)
    if not include_retired:
        stmt = stmt.where(Category.retired.is_(False))
    return list(db.scalars(stmt))


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(body: CategoryIn, db: DB, admin: AdminUser):
    if db.scalar(select(Category.id).where((Category.name == body.name) | (Category.slug == _slug(body.name)))):
        raise Conflict("A category with this name already exists")
    cat = Category(name=body.name, slug=_slug(body.name))
    db.add(cat)
    db.flush()
    audit(db, admin, "category.create", "category", cat.id, {"name": cat.name})
    db.commit()
    return cat


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, body: CategoryPatch, db: DB, admin: AdminUser):
    cat = db.get(Category, category_id)
    if cat is None:
        raise NotFound("Category not found")
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"]:
        clash = db.scalar(select(Category.id).where(Category.id != cat.id, (Category.name == changes["name"]) | (Category.slug == _slug(changes["name"]))))
        if clash:
            raise Conflict("A category with this name already exists")
        cat.name, cat.slug = " ".join(changes["name"].split()), _slug(changes["name"])
    if changes.get("retired") is not None:
        cat.retired = changes["retired"]
    audit(db, admin, "category.update", "category", cat.id, changes)
    db.commit()
    return cat
