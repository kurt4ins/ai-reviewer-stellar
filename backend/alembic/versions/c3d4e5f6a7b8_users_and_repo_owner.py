"""users table and repositories.user_id

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-16 03:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = 'c3d4e5f6a7b8'
down_revision: str | Sequence[str] | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.add_column(
        'repositories',
        sa.Column('user_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_index('ix_repositories_user_id', 'repositories', ['user_id'])
    op.create_foreign_key(
        'fk_repositories_user_id',
        'repositories',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_repositories_user_id', 'repositories', type_='foreignkey')
    op.drop_index('ix_repositories_user_id', table_name='repositories')
    op.drop_column('repositories', 'user_id')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
