"""Initial schema — users, apps, error_logs

Revision ID: 0001
Revises:
Create Date: 2026-03-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "billing_type",
            sa.Enum("free", "paid", name="billingtype"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "admin", name="userroles"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=True)

    op.create_table(
        "apps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("subdomain", sa.Text(), nullable=True),
        sa.Column("repo_url", sa.String(), nullable=False),
        sa.Column("internal_port", sa.Integer(), nullable=True),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("build_path", sa.String(), nullable=False),
        sa.Column("dockerfile_path", sa.String(), nullable=False),
        sa.Column("container_port", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("created", "running", "error", "prepared", name="appstatus"),
            nullable=False,
        ),
        sa.Column("env", sa.JSON(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "container_port >= 1024 AND container_port <= 65535",
            name="valid_port_range",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_apps_id"), "apps", ["id"], unique=False)
    op.create_index(op.f("ix_apps_subdomain"), "apps", ["subdomain"], unique=True)

    op.create_table(
        "error_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("error_code", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_error_logs_app_id"), "error_logs", ["app_id"], unique=False)
    op.create_index(op.f("ix_error_logs_error_code"), "error_logs", ["error_code"], unique=False)
    op.create_index(op.f("ix_error_logs_id"), "error_logs", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_error_logs_id"), table_name="error_logs")
    op.drop_index(op.f("ix_error_logs_error_code"), table_name="error_logs")
    op.drop_index(op.f("ix_error_logs_app_id"), table_name="error_logs")
    op.drop_table("error_logs")

    op.drop_index(op.f("ix_apps_subdomain"), table_name="apps")
    op.drop_index(op.f("ix_apps_id"), table_name="apps")
    op.drop_table("apps")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    sa.Enum(name="appstatus").drop(op.get_bind())
    sa.Enum(name="billingtype").drop(op.get_bind())
    sa.Enum(name="userroles").drop(op.get_bind())
