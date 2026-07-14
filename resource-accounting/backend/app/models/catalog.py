import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.base import Timestamped, UUIDPk

RESOURCE_ROLES = (
    "resource_admin",
    "resource_operator",
    "resource_reviewer",
    "resource_viewer",
    "resource_meter_entry",  # полевой контролёр: только ввод показаний (одна страница)
)


class Tenant(Base, UUIDPk, Timestamped):
    __tablename__ = "tenants"

    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class User(Base, UUIDPk, Timestamped):
    """Local account of the resource service; external_id links to the UK user."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id", name="uq_users_tenant_external"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)  # UK user id / telegram id
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="resource_viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ObjectType(Base, UUIDPk, Timestamped):
    __tablename__ = "object_types"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_object_types_tenant_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ResourceObject(Base, UUIDPk, Timestamped):
    __tablename__ = "resource_objects"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    type_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("object_types.id"))
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resource_objects.id"))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped["ResourceObject | None"] = relationship(remote_side="ResourceObject.id")
    type: Mapped[ObjectType | None] = relationship()
    tags: Mapped[list["Tag"]] = relationship(secondary="object_tags", lazy="selectin")


class Tag(Base, UUIDPk, Timestamped):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ObjectTag(Base):
    __tablename__ = "object_tags"
    __table_args__ = (UniqueConstraint("object_id", "tag_id", name="uq_object_tags_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resource_objects.id"), nullable=False)
    tag_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tags.id"), nullable=False)


class Provider(Base, UUIDPk, Timestamped):
    __tablename__ = "providers"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_providers_tenant_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact: Mapped[str | None] = mapped_column(Text)
    # Export template config: column order/labels/file name pattern (reserved, JSON)
    export_template: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
