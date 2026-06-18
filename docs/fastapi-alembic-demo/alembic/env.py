"""Alembic 迁移环境配置

关键点：
- target_metadata 指向 ORM 模型的 Base.metadata
- 这样可以 --autogenerate 自动对比模型和实际数据库的差异
"""

import sys
from pathlib import Path

# 确保 demo 的 app/ 优先于项目其他同名模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from alembic import context
from sqlalchemy import engine_from_config, pool

# 从 demo 的 app.models 导入 Base
from app.models import Base

target_metadata = Base.metadata

def run_migrations_offline():
    """离线模式：生成 SQL 不执行（用于预览/审核）"""
    url = "sqlite:///demo.db"
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """在线模式：连接数据库并执行迁移"""
    connectable = engine_from_config(
        {"sqlalchemy.url": "sqlite:///demo.db"},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
