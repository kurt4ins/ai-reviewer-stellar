"""initial schema

Revision ID: e0754e9f8f02
Revises:
Create Date: 2026-05-15 23:55:58.156558

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e0754e9f8f02'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'repositories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('provider', sa.String(length=16), nullable=False),
        sa.Column('owner', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('encrypted_token', sa.Text(), nullable=False),
        sa.Column('webhook_secret', sa.String(length=255), nullable=False),
        sa.Column('ignore_globs', sa.JSON(), nullable=False),
        sa.Column('block_critical_merge', sa.Boolean(), nullable=False),
        sa.Column('dialog_enabled', sa.Boolean(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'owner', 'name', name='uq_repo_identity'),
    )


def downgrade() -> None:
    op.drop_table('repositories')
