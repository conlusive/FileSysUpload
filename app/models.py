"""ORM-моделі: користувачі та збережені файли."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base


class UTCDateTime(TypeDecorator):
    """DateTime, що зберігається як UTC і завжди повертається з часовим поясом."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return None if value is None else value.replace(tzinfo=timezone.utc)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    files: Mapped[list["StoredFile"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )


class StoredFile(Base):
    __tablename__ = "files"
    __table_args__ = (Index("ix_files_owner_created", "owner_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # uuid4().hex
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16))              # image | document
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stored_name: Mapped[str] = mapped_column(String(64))
    optimized_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    optimized_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    thumbnail_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thumbnail_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    variant_mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    owner: Mapped[User] = relationship(back_populates="files")
