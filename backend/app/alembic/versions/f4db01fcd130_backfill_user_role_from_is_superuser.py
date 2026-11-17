"""Backfill user.role from is_superuser (data step)

Maps the old access model onto roles with no privilege change:
is_superuser = true -> 'admin'; everyone else stays 'member'. Nobody becomes
'manager' by migration. The upgrade verifies the result by reading it back and
aborts (rolling back the transaction) if admins != former superusers.

`is_superuser` is kept and kept in sync by the app (is_superuser = role ==
admin), so rolling the code back stays safe. Dropping it is a later migration.

Revision ID: f4db01fcd130
Revises: 28caf424a4a6
Create Date: 2026-11-17 12:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4db01fcd130'
down_revision = '28caf424a4a6'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("""UPDATE "user" SET role = 'admin' WHERE is_superuser"""))

    mismatched = conn.execute(
        sa.text(
            """SELECT count(*) FROM "user"
               WHERE (role = 'admin') IS DISTINCT FROM is_superuser"""
        )
    ).scalar_one()
    if mismatched:
        raise RuntimeError(
            f"role backfill mismatch: {mismatched} user(s) where "
            "role = 'admin' does not equal is_superuser; aborting"
        )


def downgrade():
    op.execute("""UPDATE "user" SET role = 'member'""")
