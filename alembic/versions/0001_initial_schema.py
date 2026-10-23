"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-15 07:44:41.755068
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table('badges',
    sa.Column('key', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.String(length=500), nullable=False),
    sa.Column('criterion', sa.Enum('volunteer', 'testcases', 'artifacts', 'presentations', 'topics', name='badge_criterion', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('threshold', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('threshold >= 1', name=op.f('ck_badges_threshold_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_badges')),
    sa.UniqueConstraint('key', name='uq_badges_key')
    )
    op.create_table('categories',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('retired', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories')),
    sa.UniqueConstraint('name', name='uq_categories_name'),
    sa.UniqueConstraint('slug', name='uq_categories_slug')
    )
    op.create_table('integration_state',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_integration_state'))
    )
    op.create_table('job_executions',
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('status', sa.Enum('running', 'succeeded', 'failed', 'skipped', name='job_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('result', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_executions')),
    sa.UniqueConstraint('idempotency_key', name='uq_job_executions_idempotency_key')
    )
    op.create_index('ix_job_executions_name_started', 'job_executions', ['name', 'started_at'], unique=False)
    op.create_table('users',
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('entra_object_id', sa.String(length=64), nullable=True),
    sa.Column('role', sa.Enum('Employee', 'Admin', 'Moderator', name='user_role', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('team', sa.String(length=100), nullable=True),
    sa.Column('job_title', sa.String(length=200), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('email = lower(email)', name=op.f('ck_users_email_lowercase')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name='uq_users_email'),
    sa.UniqueConstraint('entra_object_id', name='uq_users_entra_object_id')
    )
    op.create_index('ix_users_role', 'users', ['role'], unique=False)
    op.create_table('agent_runs',
    sa.Column('workflow', sa.String(length=80), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled', name='run_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=True),
    sa.Column('input', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('output', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('parent_run_id', sa.Uuid(), nullable=True),
    sa.Column('celery_task_id', sa.String(length=64), nullable=True),
    sa.Column('triggered_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('attempts >= 0', name=op.f('ck_agent_runs_attempts_non_negative')),
    sa.ForeignKeyConstraint(['parent_run_id'], ['agent_runs.id'], name=op.f('fk_agent_runs_parent_run_id_agent_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['triggered_by'], ['users.id'], name=op.f('fk_agent_runs_triggered_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_runs')),
    sa.UniqueConstraint('idempotency_key', name='uq_agent_runs_idempotency_key')
    )
    op.create_index('ix_agent_runs_status_created', 'agent_runs', ['status', 'created_at'], unique=False)
    op.create_index('ix_agent_runs_workflow', 'agent_runs', ['workflow'], unique=False)
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], name=op.f('fk_app_settings_updated_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings'))
    )
    op.create_table('audit_logs',
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_label', sa.String(length=320), nullable=False),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('target_type', sa.String(length=60), nullable=False),
    sa.Column('target_id', sa.String(length=64), nullable=True),
    sa.Column('details', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('request_id', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_audit_logs_actor_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)
    op.create_index('ix_audit_logs_actor', 'audit_logs', ['actor_id'], unique=False)
    op.create_index('ix_audit_logs_created', 'audit_logs', ['created_at'], unique=False)
    op.create_index('ix_audit_logs_target', 'audit_logs', ['target_type', 'target_id'], unique=False)
    op.create_table('notifications',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=60), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('channel', sa.Enum('in_app', 'email', 'teams', 'buddy', name='notification_channel', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('pending', 'sent', 'failed', 'skipped', name='notification_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('dedupe_key', sa.String(length=200), nullable=True),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notifications_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('user_id', 'channel', 'dedupe_key', name='uq_notifications_user_channel_dedupe')
    )
    op.create_index('ix_notifications_status_channel', 'notifications', ['status', 'channel'], unique=False)
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'], unique=False)
    op.create_table('technology_sources',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('kind', sa.Enum('feed', name='source_kind', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=True),
    sa.Column('last_crawled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('consecutive_failures >= 0', name=op.f('ck_technology_sources_failures_non_negative')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_technology_sources_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_technology_sources_created_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_technology_sources')),
    sa.UniqueConstraint('url', name='uq_technology_sources_url')
    )
    op.create_index('ix_technology_sources_enabled', 'technology_sources', ['enabled'], unique=False)
    op.create_table('user_badges',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('badge_id', sa.Uuid(), nullable=False),
    sa.Column('awarded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('awarded_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['awarded_by'], ['users.id'], name=op.f('fk_user_badges_awarded_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['badge_id'], ['badges.id'], name=op.f('fk_user_badges_badge_id_badges'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_badges_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_badges')),
    sa.UniqueConstraint('user_id', 'badge_id', name='uq_user_badges_user_badge')
    )
    op.create_index(op.f('ix_user_badges_user_id'), 'user_badges', ['user_id'], unique=False)
    op.create_table('agent_checkpoints',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('step', sa.String(length=100), nullable=False),
    sa.Column('state', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], name=op.f('fk_agent_checkpoints_run_id_agent_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_checkpoints')),
    sa.UniqueConstraint('run_id', 'step', name='uq_agent_checkpoints_run_step')
    )
    op.create_index(op.f('ix_agent_checkpoints_run_id'), 'agent_checkpoints', ['run_id'], unique=False)
    op.create_table('agent_events',
    sa.Column('run_id', sa.Uuid(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('level', sa.Enum('info', 'warning', 'error', name='event_level', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('event_type', sa.String(length=60), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], name=op.f('fk_agent_events_run_id_agent_runs'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_agent_events')),
    sa.UniqueConstraint('run_id', 'seq', name='uq_agent_events_run_seq')
    )
    op.create_index('ix_agent_events_run_seq', 'agent_events', ['run_id', 'seq'], unique=False)
    op.create_table('discovery_sessions',
    sa.Column('trigger', sa.Enum('scheduled', 'manual', name='discovery_trigger', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'succeeded', 'partial', 'failed', 'cancelled', name='discovery_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('started_by', sa.Uuid(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('stats', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('agent_run_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], name=op.f('fk_discovery_sessions_agent_run_id_agent_runs'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['started_by'], ['users.id'], name=op.f('fk_discovery_sessions_started_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_discovery_sessions'))
    )
    op.create_index('ix_discovery_sessions_created', 'discovery_sessions', ['created_at'], unique=False)
    op.create_table('topics',
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('discovered', 'enriched', 'classified', 'blocked', 'unverified', 'pending_review', 'open_for_volunteers', 'in_progress', 'rejected', 'merged', 'archived', name='topic_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('origin', sa.Enum('agent', 'custom', name='topic_origin', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('relevance_score', sa.Float(), nullable=True),
    sa.Column('fingerprint', sa.String(length=64), nullable=False),
    sa.Column('canonical_url', sa.String(length=2048), nullable=True),
    sa.Column('suggested_use_case', sa.Text(), nullable=True),
    sa.Column('low_cost_simulation', sa.Boolean(), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('flags', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('guardrail', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('discovery_session_id', sa.Uuid(), nullable=True),
    sa.Column('requested_by', sa.Uuid(), nullable=True),
    sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('merged_into_id', sa.Uuid(), nullable=True),
    sa.Column('max_volunteers', sa.Integer(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('max_volunteers IS NULL OR max_volunteers >= 1', name=op.f('ck_topics_max_volunteers_positive')),
    sa.CheckConstraint('relevance_score IS NULL OR (relevance_score >= 0 AND relevance_score <= 100)', name=op.f('ck_topics_relevance_range')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_topics_category_id_categories'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['discovery_session_id'], ['discovery_sessions.id'], name=op.f('fk_topics_discovery_session_id_discovery_sessions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['merged_into_id'], ['topics.id'], name=op.f('fk_topics_merged_into_id_topics'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name=op.f('fk_topics_requested_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name=op.f('fk_topics_reviewed_by_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_topics'))
    )
    op.create_index('ix_topics_category', 'topics', ['category_id'], unique=False)
    op.create_index('ix_topics_fingerprint', 'topics', ['fingerprint'], unique=False)
    op.create_index('ix_topics_status_detected', 'topics', ['status', 'detected_at'], unique=False)
    op.create_table('certificates',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('serial', sa.String(length=40), nullable=False),
    sa.Column('storage_key', sa.String(length=512), nullable=True),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_certificates_topic_id_topics'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_certificates_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_certificates')),
    sa.UniqueConstraint('serial', name='uq_certificates_serial'),
    sa.UniqueConstraint('user_id', 'topic_id', name='uq_certificates_user_topic')
    )
    op.create_index(op.f('ix_certificates_user_id'), 'certificates', ['user_id'], unique=False)
    op.create_table('invitations',
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('invited_by', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'accepted', 'declined', 'expired', 'revoked', name='invitation_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_reminded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reminder_count', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], name=op.f('fk_invitations_invited_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_invitations_topic_id_topics'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_invitations_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_invitations')),
    sa.UniqueConstraint('topic_id', 'user_id', name='uq_invitations_topic_user')
    )
    op.create_index('ix_invitations_status_expires', 'invitations', ['status', 'expires_at'], unique=False)
    op.create_index('ix_invitations_user_status', 'invitations', ['user_id', 'status'], unique=False)
    op.create_table('source_articles',
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('source_id', sa.Uuid(), nullable=True),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('url_hash', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=500), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('excerpt', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('verification', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['technology_sources.id'], name=op.f('fk_source_articles_source_id_technology_sources'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_source_articles_topic_id_topics'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_articles')),
    sa.UniqueConstraint('topic_id', 'url_hash', name='uq_source_articles_topic_url')
    )
    op.create_index(op.f('ix_source_articles_topic_id'), 'source_articles', ['topic_id'], unique=False)
    op.create_index('ix_source_articles_url_hash', 'source_articles', ['url_hash'], unique=False)
    op.create_table('topic_reviews',
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('reviewer_id', sa.Uuid(), nullable=True),
    sa.Column('decision', sa.Enum('approved', 'rejected', 'merged', 'verified', name='review_decision', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('changes', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_topic_reviews_reviewer_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_topic_reviews_topic_id_topics'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_topic_reviews'))
    )
    op.create_index('ix_topic_reviews_topic_created', 'topic_reviews', ['topic_id', 'created_at'], unique=False)
    op.create_table('topic_test_cases',
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_topic_test_cases_author_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_topic_test_cases_topic_id_topics'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_topic_test_cases'))
    )
    op.create_index('ix_topic_test_cases_author', 'topic_test_cases', ['author_id'], unique=False)
    op.create_index(op.f('ix_topic_test_cases_topic_id'), 'topic_test_cases', ['topic_id'], unique=False)
    op.create_table('volunteers',
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('active', 'waitlisted', 'removed', 'completed', name='volunteer_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('joined_via', sa.String(length=20), nullable=False),
    sa.Column('invitation_id', sa.Uuid(), nullable=True),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('left_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint("joined_via IN ('invitation','self','admin')", name=op.f('ck_volunteers_joined_via_valid')),
    sa.ForeignKeyConstraint(['invitation_id'], ['invitations.id'], name=op.f('fk_volunteers_invitation_id_invitations'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_volunteers_topic_id_topics'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_volunteers_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_volunteers')),
    sa.UniqueConstraint('topic_id', 'user_id', name='uq_volunteers_topic_user')
    )
    op.create_index('ix_volunteers_topic_status', 'volunteers', ['topic_id', 'status'], unique=False)
    op.create_index('ix_volunteers_user_status', 'volunteers', ['user_id', 'status'], unique=False)
    op.create_table('assignments',
    sa.Column('volunteer_id', sa.Uuid(), nullable=False),
    sa.Column('topic_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('stage', sa.Enum('Study', 'POC', 'Presentation', name='assignment_stage', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Enum('open', 'completed', 'cancelled', name='assignment_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_reminded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_assignments_topic_id_topics'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_assignments_user_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['volunteer_id'], ['volunteers.id'], name=op.f('fk_assignments_volunteer_id_volunteers'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_assignments')),
    sa.UniqueConstraint('volunteer_id', 'stage', name='uq_assignments_volunteer_stage')
    )
    op.create_index('ix_assignments_status_due', 'assignments', ['status', 'due_at'], unique=False)
    op.create_index('ix_assignments_topic', 'assignments', ['topic_id'], unique=False)
    op.create_index('ix_assignments_user', 'assignments', ['user_id'], unique=False)
    op.create_table('artifacts',
    sa.Column('author_id', sa.Uuid(), nullable=False),
    sa.Column('topic_id', sa.Uuid(), nullable=True),
    sa.Column('assignment_id', sa.Uuid(), nullable=True),
    sa.Column('stage', sa.Enum('Study', 'POC', 'Presentation', name='artifact_stage', native_enum=False, create_constraint=True, length=32), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('type', sa.Enum('poc', 'architecture_pattern', 'codebase', 'document', 'presentation', 'use_case', name='artifact_type', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('status', sa.Enum('submitted', 'scanning', 'quarantined', 'pending_review', 'approved', 'rejected', name='artifact_status', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=True),
    sa.Column('content_type', sa.String(length=120), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=True),
    sa.Column('storage_key', sa.String(length=512), nullable=True),
    sa.Column('repo_url', sa.String(length=2048), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('scan_result', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('reviewed_by', sa.Uuid(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejection_reason', sa.Text(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sharepoint_item_id', sa.String(length=200), nullable=True),
    sa.Column('sharepoint_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('sync_error', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.CheckConstraint('size_bytes >= 0', name=op.f('ck_artifacts_size_non_negative')),
    sa.CheckConstraint('version >= 1', name=op.f('ck_artifacts_version_positive')),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], name=op.f('fk_artifacts_assignment_id_assignments'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_artifacts_author_id_users'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name=op.f('fk_artifacts_reviewed_by_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['topics.id'], name=op.f('fk_artifacts_topic_id_topics'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_artifacts'))
    )
    op.create_index('ix_artifacts_author', 'artifacts', ['author_id'], unique=False)
    op.create_index('ix_artifacts_sha256', 'artifacts', ['sha256'], unique=False)
    op.create_index('ix_artifacts_status_created', 'artifacts', ['status', 'created_at'], unique=False)
    op.create_index('ix_artifacts_topic', 'artifacts', ['topic_id'], unique=False)
    op.create_table('moderation_records',
    sa.Column('artifact_id', sa.Uuid(), nullable=False),
    sa.Column('moderator_id', sa.Uuid(), nullable=True),
    sa.Column('decision', sa.Enum('approved', 'rejected', 'quarantined', name='moderation_decision', native_enum=False, create_constraint=True, length=32), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('scan_snapshot', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['artifact_id'], ['artifacts.id'], name=op.f('fk_moderation_records_artifact_id_artifacts'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['moderator_id'], ['users.id'], name=op.f('fk_moderation_records_moderator_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_moderation_records'))
    )
    op.create_index('ix_moderation_records_artifact', 'moderation_records', ['artifact_id', 'created_at'], unique=False)



def downgrade() -> None:

    op.drop_index('ix_moderation_records_artifact', table_name='moderation_records')
    op.drop_table('moderation_records')
    op.drop_index('ix_artifacts_topic', table_name='artifacts')
    op.drop_index('ix_artifacts_status_created', table_name='artifacts')
    op.drop_index('ix_artifacts_sha256', table_name='artifacts')
    op.drop_index('ix_artifacts_author', table_name='artifacts')
    op.drop_table('artifacts')
    op.drop_index('ix_assignments_user', table_name='assignments')
    op.drop_index('ix_assignments_topic', table_name='assignments')
    op.drop_index('ix_assignments_status_due', table_name='assignments')
    op.drop_table('assignments')
    op.drop_index('ix_volunteers_user_status', table_name='volunteers')
    op.drop_index('ix_volunteers_topic_status', table_name='volunteers')
    op.drop_table('volunteers')
    op.drop_index(op.f('ix_topic_test_cases_topic_id'), table_name='topic_test_cases')
    op.drop_index('ix_topic_test_cases_author', table_name='topic_test_cases')
    op.drop_table('topic_test_cases')
    op.drop_index('ix_topic_reviews_topic_created', table_name='topic_reviews')
    op.drop_table('topic_reviews')
    op.drop_index('ix_source_articles_url_hash', table_name='source_articles')
    op.drop_index(op.f('ix_source_articles_topic_id'), table_name='source_articles')
    op.drop_table('source_articles')
    op.drop_index('ix_invitations_user_status', table_name='invitations')
    op.drop_index('ix_invitations_status_expires', table_name='invitations')
    op.drop_table('invitations')
    op.drop_index(op.f('ix_certificates_user_id'), table_name='certificates')
    op.drop_table('certificates')
    op.drop_index('ix_topics_status_detected', table_name='topics')
    op.drop_index('ix_topics_fingerprint', table_name='topics')
    op.drop_index('ix_topics_category', table_name='topics')
    op.drop_table('topics')
    op.drop_index('ix_discovery_sessions_created', table_name='discovery_sessions')
    op.drop_table('discovery_sessions')
    op.drop_index('ix_agent_events_run_seq', table_name='agent_events')
    op.drop_table('agent_events')
    op.drop_index(op.f('ix_agent_checkpoints_run_id'), table_name='agent_checkpoints')
    op.drop_table('agent_checkpoints')
    op.drop_index(op.f('ix_user_badges_user_id'), table_name='user_badges')
    op.drop_table('user_badges')
    op.drop_index('ix_technology_sources_enabled', table_name='technology_sources')
    op.drop_table('technology_sources')
    op.drop_index('ix_notifications_user_created', table_name='notifications')
    op.drop_index('ix_notifications_status_channel', table_name='notifications')
    op.drop_table('notifications')
    op.drop_index('ix_audit_logs_target', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_table('app_settings')
    op.drop_index('ix_agent_runs_workflow', table_name='agent_runs')
    op.drop_index('ix_agent_runs_status_created', table_name='agent_runs')
    op.drop_table('agent_runs')
    op.drop_index('ix_users_role', table_name='users')
    op.drop_table('users')
    op.drop_index('ix_job_executions_name_started', table_name='job_executions')
    op.drop_table('job_executions')
    op.drop_table('integration_state')
    op.drop_table('categories')
    op.drop_table('badges')

