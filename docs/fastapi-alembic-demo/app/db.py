"""数据库连接 + ORM Base 定义"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

# 数据库文件放在 demo 根目录
DB_PATH = Path(__file__).parent.parent / "demo.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False)


class Base(DeclarativeBase):
    """所有 ORM 模型继承的基类。通过 Base.metadata 注册表结构。"""
    pass
