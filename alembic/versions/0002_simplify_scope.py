"""simplify scope: no relevance score, no source pause flag, Moderator merged into Admin

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23 16:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    postgres = bind.dialect.name == 'postgresql'
    op.drop_index('ix_technology_sources_enabled', table_name='technology_sources')
    if postgres:
        op.drop_constraint(op.f('ck_topics_relevance_range'), 'topics', type_='check')
        op.drop_column('topics', 'relevance_score')
        op.drop_column('technology_sources', 'enabled')
    else:  # SQLite (tests, local experiments): rebuild the tables without the columns
        with op.batch_alter_table('topics') as batch:
            batch.drop_column('relevance_score')
        with op.batch_alter_table('technology_sources') as batch:
            batch.drop_column('enabled')
    # The Moderator role no longer exists in the product: those people become Admins.
    op.execute("UPDATE users SET role = 'Admin' WHERE role = 'Moderator'")


def downgrade() -> None:
    op.add_column('technology_sources', sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index('ix_technology_sources_enabled', 'technology_sources', ['enabled'], unique=False)
    op.add_column('topics', sa.Column('relevance_score', sa.Float(), nullable=True))
    if op.get_bind().dialect.name == 'postgresql':
        op.create_check_constraint(op.f('ck_topics_relevance_range'), 'topics',
                                   'relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 100)')
    # users that were Moderators stay Admins
