"""add archived to sender_status enum

Revision ID: a1b2c3d4e5f6
Revises: 64496324b848
Create Date: 2026-04-25 07:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = '64496324b848'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add 'archived' value to sender_status enum."""
    with op.batch_alter_table('senders', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(
                'active', 'unsubscribed', 'whitelisted', 'trashed',
                name='sender_status',
            ),
            type_=sa.Enum(
                'active', 'unsubscribed', 'whitelisted', 'trashed', 'archived',
                name='sender_status',
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Remove 'archived' value from sender_status enum."""
    with op.batch_alter_table('senders', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(
                'active', 'unsubscribed', 'whitelisted', 'trashed', 'archived',
                name='sender_status',
            ),
            type_=sa.Enum(
                'active', 'unsubscribed', 'whitelisted', 'trashed',
                name='sender_status',
            ),
            existing_nullable=False,
        )
