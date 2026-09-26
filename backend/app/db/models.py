"""Модель данных PostgreSQL.

Каталог хранит происхождение каждой характеристики (источник, подтверждённость) в
поле specs. Сценарий проекта хранит входные данные, результат и версии каталога и
расчётной модели, чтобы расчёт можно было воспроизвести позже (п. 3.1.5 ТЗ).
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    data: Mapped[dict] = mapped_column(JSON)               # вся карточка решения
    name: Mapped[str] = mapped_column(String(512), index=True)
    subtype: Mapped[str] = mapped_column(String(128), default="", index=True)
    price_rub: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String(128), default="etl")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))   # pbkdf2, пароли не храним
    role: Mapped[str] = mapped_column(String(16), default="user")   # user / admin
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(256))
    object_type: Mapped[str] = mapped_column(String(32))
    profile_code: Mapped[str] = mapped_column(String(64), default="")
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)
    scenarios: Mapped[list["Scenario"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Scenario.id")


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(256))
    solution_external_id: Mapped[str] = mapped_column(String(64))
    profile_code: Mapped[str] = mapped_column(String(64))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)     # ключевые цифры
    catalog_version: Mapped[str] = mapped_column(String(32), default="")
    model_version: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    project: Mapped[Project] = relationship(back_populates="scenarios")


class Setting(Base):
    """Расчётные нормативы по умолчанию, изменённые администратором."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)
