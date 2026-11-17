"""Drop user.is_superuser (drop step)

`role` replaced `is_superuser` in revisions 28caf424a4a6 / f4db01fcd130, and
the app has not read `is_superuser` since. Ship this only after every app
instance runs code without the `is_superuser` field.

Downgrade restores the column from `role` (admin -> true, else false), so
the previous code version works again. Managers come back as non-superusers;
nobody gains privileges.

Revision ID: 647626730528
Revises: f4db01fcd130
Create Date: 2026-11-17 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '647626730528'
down_revision = 'f4db01fcd130'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('user', 'is_superuser')


def downgrade():
    op.add_column(
        'user',
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("""UPDATE "user" SET is_superuser = (role = 'admin')""")
    op.alter_column('user', 'is_superuser', server_default=None)
