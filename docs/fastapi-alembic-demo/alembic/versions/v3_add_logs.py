"""v3: 加 logs 表 + 迁移关联数据

Revision ID: v003
Revises: v002
"""

from alembic import op
import sqlalchemy as sa

revision = "v003"
down_revision = "v002"
branch_labels = None
depends_on = None


def upgrade():
    # 建新表
    op.create_table(
        "logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("detail", sa.String(200), nullable=False, server_default=""),
    )

    # 数据迁移：为每个已有用户生成一条初始日志
    conn = op.get_bind()
    users = conn.execute(
        sa.text("SELECT id, name, created_at FROM users")
    ).mappings().all()
    for u in users:
        conn.execute(
            sa.text(
                "INSERT INTO logs (user_id, action, detail) "
                "VALUES (:uid, 'account_created', :detail)"
            ),
            {"uid": u["id"], "detail": f"用户 {u['name']} 于 {u['created_at']} 注册"},
        )


def downgrade():
    op.drop_table("logs")
