"""reviews, findings, review_threads

Revision ID: a1b2c3d4e5f6
Revises: e0754e9f8f02
Create Date: 2026-05-16 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: str | Sequence[str] | None = 'e0754e9f8f02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reviews',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('repository_id', sa.UUID(), nullable=False),
        sa.Column('pr_number', sa.Integer(), nullable=False),
        sa.Column('commit_sha', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('findings_count', sa.Integer(), nullable=False),
        sa.Column('critical_count', sa.Integer(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['repository_id'], ['repositories.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_reviews_repository_id', 'reviews', ['repository_id'], unique=False
    )

    op.create_table(
        'findings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('review_id', sa.UUID(), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('cwe', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('fix_code', sa.Text(), nullable=True),
        sa.Column('fix_explanation', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ['review_id'], ['reviews.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_findings_review_id', 'findings', ['review_id'], unique=False
    )

    op.create_table(
        'review_threads',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('finding_id', sa.UUID(), nullable=False),
        sa.Column('provider_comment_id', sa.String(length=64), nullable=True),
        sa.Column('messages_json', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ['finding_id'], ['findings.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_review_threads_finding_id',
        'review_threads',
        ['finding_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_review_threads_finding_id', table_name='review_threads')
    op.drop_table('review_threads')
    op.drop_index('ix_findings_review_id', table_name='findings')
    op.drop_table('findings')
    op.drop_index('ix_reviews_repository_id', table_name='reviews')
    op.drop_table('reviews')
