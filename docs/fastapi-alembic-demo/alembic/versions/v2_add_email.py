"""v2: 加 email 列 + 数据回填（★ 数据迁移的核心示例）

Revision ID: v002
Revises: v001  (链向上一个版本)

关键点：
  1. --autogenerate 只能生成 ADD COLUMN，不会生成数据回填
  2. 数据迁移需要手写在 upgrade() 里
  3. op.get_bind() 拿到数据库连接 → 执行 UPDATE
  4. 分三步保护数据：nullable 加列 → 回填 → 加 NOT NULL 约束
"""

from alembic import op
import sqlalchemy as sa

revision = "v002"
down_revision = "v001"
branch_labels = None
depends_on = None


def upgrade():
    # 第1步：先加列，允许 NULL（v1 的老数据还没有 email 值）
    op.add_column(
        "users",
        sa.Column("email", sa.String(100), nullable=True),
    )

    # 第2步：★ 数据迁移 —— 从现有数据生成 email 并回填
    #         --autogenerate 不会生成这段，必须手写
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM users")).mappings().all()
    for row in rows:
        email = f"{row['name']}@example.com"
        conn.execute(
            sa.text("UPDATE users SET email = :email WHERE id = :id"),
            {"email": email, "id": row["id"]},
        )

    # 第3步：SQLite 不支持 ALTER COLUMN SET NOT NULL
    #        跳过这步；PostgreSQL / MySQL 则执行
    #        with op.get_context().begin_transaction():
    #            op.alter_column("users", "email", nullable=False)


def downgrade():
    op.drop_column("users", "email")
