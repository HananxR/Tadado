"""ORM 模型：每个类对应数据库中的一张表"""

from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    created_at: Mapped[str] = mapped_column()
    email: Mapped[str] = mapped_column()    # v2 新增



class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column()
    action: Mapped[str] = mapped_column()
    detail: Mapped[str] = mapped_column()
