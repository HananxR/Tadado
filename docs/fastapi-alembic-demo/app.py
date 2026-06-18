"""启动入口（兼容旧运行方式）

    uv run python app.py
    或
    uv run uvicorn app.main:app --port 8000
"""
from app.main import app
from app.db import DB_PATH
from app.main import run_migrations

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  FastAPI + Alembic 迁移演示")
    print("=" * 60)
    run_migrations()
    print(f"  数据库就绪: {DB_PATH}")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
