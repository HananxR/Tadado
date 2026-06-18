"""FastAPI 应用 + Alembic 迁移入口

启动方式：
    cd docs/fastapi-alembic-demo
    uv run uvicorn app.main:app --port 8000
"""

from pathlib import Path
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session
from alembic.config import Config
from alembic import command

from app.db import engine, DATABASE_URL, DB_PATH

app = FastAPI(title="Alembic 迁移演示")


def run_migrations():
    """应用启动时执行 Alembic 迁移到最新版本"""
    alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(alembic_cfg, "head")


@app.on_event("startup")
def on_startup():
    print(f"  数据库: {DB_PATH}")
    run_migrations()
    print("  迁移完成")


@app.get("/")
def list_users():
    """查看 users 表（验证 v1→v2 的 email 回填）"""
    with Session(engine) as sess:
        rows = sess.execute(text("SELECT * FROM users")).mappings().all()
        return {
            "table": "users",
            "rows": [dict(r) for r in rows],
        }


@app.get("/logs")
def list_logs():
    """查看 logs 表（验证 v3 的数据迁移）"""
    with Session(engine) as sess:
        rows = sess.execute(text("SELECT * FROM logs")).mappings().all()
        return {
            "table": "logs",
            "rows": [dict(r) for r in rows],
        }


@app.get("/version")
def get_version():
    with Session(engine) as sess:
        row = sess.execute(
            text("SELECT version_num FROM alembic_version")
        ).fetchone()
        return {"alembic_version": row[0] if row else "unknown"}
