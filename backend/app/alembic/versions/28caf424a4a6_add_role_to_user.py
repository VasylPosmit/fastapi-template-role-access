"""Add role to user (schema step)

Adds `user.role` as NOT NULL with server default 'member'. Postgres fills the
default into every existing row without a table rewrite, so after this step all
existing users are members; the next revision promotes former superusers.
Allowed values are validated in code (app.core.permissions.Role), not by a DB
constraint, so adding a role later needs no migration.

Revision ID: 28caf424a4a6
Revises: fe56fa70289e
Create Date: 2026-11-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '28caf424a4a6'
down_revision = 'fe56fa70289e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user',
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
    )


def downgrade():
    op.drop_column('user', 'role')
