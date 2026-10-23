import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.api.deps import DB, AdminUser
from app.core.config import Settings, get_settings
from app.core.errors import Conflict, NotFound, Unprocessable
from app.db.models import Category, TechnologySource
from app.schemas.common import Page, PageParams, paginate
from app.schemas.topics import SourceIn, SourceOut, SourcePatch
from app.security.ssrf import BlockedURLError, FetchError, validate_url
from app.services.audit import audit

router = APIRouter(prefix="/sources", tags=["sources"])


def _check_url(url: str, settings: Settings) -> None:
    """Refuse internal addresses when the source is registered (and again at every fetch)."""
    try:
        validate_url(url, allowed_ports=settings.fetch_port_list)
    except BlockedURLError as exc:
        raise Unprocessable(f"This URL is not allowed: {exc}") from exc
    except FetchError as exc:
        raise Unprocessable(f"This URL could not be checked: {exc}") from exc


@router.get("", response_model=Page[SourceOut])
def list_sources(db: DB, _: AdminUser, params: PageParams = Depends()):
    stmt = select(TechnologySource).order_by(TechnologySource.name)
    rows, total = paginate(db, stmt, params)
    return Page(items=rows, total=total, limit=params.limit, offset=params.offset)


@router.post("", response_model=SourceOut, status_code=201)
def create_source(body: SourceIn, db: DB, admin: AdminUser, settings: Settings = Depends(get_settings)):
    url = str(body.url)
    _check_url(url, settings)
    if db.scalar(select(TechnologySource.id).where(TechnologySource.url == url)):
        raise Conflict("This source is already registered")
    if body.category_id and db.get(Category, body.category_id) is None:
        raise Unprocessable("Category not found")
    src = TechnologySource(name=body.name, url=url, category_id=body.category_id, created_by=admin.id)
    db.add(src)
    db.flush()
    audit(db, admin, "source.create", "source", src.id, {"url": url})
    db.commit()
    return src


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(source_id: uuid.UUID, body: SourcePatch, db: DB, admin: AdminUser):
    src = db.get(TechnologySource, source_id)
    if src is None:
        raise NotFound("Source not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        if v is not None or k == "category_id":
            setattr(src, k, v)
    audit(db, admin, "source.update", "source", src.id, {k: str(v) for k, v in changes.items()})
    db.commit()
    return src


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: uuid.UUID, db: DB, admin: AdminUser):
    src = db.get(TechnologySource, source_id)
    if src is None:
        raise NotFound("Source not found")
    audit(db, admin, "source.delete", "source", src.id, {"url": src.url})
    db.delete(src)
    db.commit()
