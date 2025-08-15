# app/models.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import text

# ✨ 필요한 타입들 모두 임포트
from sqlalchemy import BigInteger, Float, ForeignKey, Text, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

# ✅ MySQL 전용 DATETIME(fsp=6)
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime
# (점수 컬럼을 DOUBLE로 고정하려면 위 Float 대신 아래를 사용)
# from sqlalchemy.dialects.mysql import DOUBLE as MySQLDouble

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)")
    )

    scores: Mapped[list["Score"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column("text", Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # score: Mapped[float] = mapped_column(MySQLDouble, nullable=False)  # 쓰려면 활성화

    created_at: Mapped[datetime] = mapped_column(
        MySQLDateTime(fsp=6),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)")
    )

    user: Mapped["User"] = relationship(back_populates="scores")


Index("idx_scores_user_created", Score.user_id, Score.created_at)
