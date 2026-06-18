"""v1: 创建 users 表（初始版本）

Revision ID: v001
Revises: None  (根节点——版本链起点)
"""

from alembic import op
import sqlalchemy as sa

revision = "v001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("created_at", sa.String(19), nullable=False, server_default=""),
    )
    # 种子数据：插入 3 条初始记录
    op.execute("INSERT INTO users (name, created_at) VALUES ('张三', '2025-01-01 10:00:00')")
    op.execute("INSERT INTO users (name, created_at) VALUES ('李四', '2025-01-15 14:30:00')")
    op.execute("INSERT INTO users (name, created_at) VALUES ('王五', '2025-02-20 09:00:00')")


def downgrade():
    op.drop_table("users")
