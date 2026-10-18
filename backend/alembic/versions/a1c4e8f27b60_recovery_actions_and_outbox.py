"""extend recovery actions and add transactional outbox

Revision ID: a1c4e8f27b60
Revises: efa47067e459
Create Date: 2026-10-19 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'a1c4e8f27b60'
down_revision: Union[str, Sequence[str], None] = 'efa47067e459'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

T = 'workflow_recovery_actions'
ACTIONS = "action_type IN ('retry_workflow', 'reconcile_and_resume', 'mark_for_review')"
STATUSES = "status IN ('requested', 'approved', 'rejected', 'queued', 'executing', 'executed', 'failed')"
OLD_ACTIONS = "action IN ('retry', 'manual_review', 'no_action')"
OLD_STATUSES = "status IN ('requested', 'approved', 'rejected', 'executed', 'failed')"


def upgrade() -> None:
    op.drop_constraint(op.f('ck_workflow_recovery_actions_action_valid'), T, type_='check')
    op.drop_constraint(op.f('ck_workflow_recovery_actions_status_valid'), T, type_='check')

    op.alter_column(T, 'action', new_column_name='action_type')
    op.execute(
        "UPDATE workflow_recovery_actions SET action_type = CASE action_type "
        "WHEN 'retry' THEN 'retry_workflow' ELSE 'mark_for_review' END"
    )
    op.execute("UPDATE workflow_recovery_actions SET reason = 'n/a' WHERE reason IS NULL")
    op.alter_column(T, 'reason', existing_type=sa.Text(), nullable=False)

    op.add_column(T, sa.Column('approved_by', sa.UUID(), nullable=True))
    op.add_column(T, sa.Column('rejected_by', sa.UUID(), nullable=True))
    op.add_column(T, sa.Column('rejection_reason', sa.Text(), nullable=True))
    op.add_column(T, sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column(T, sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(T, sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column(T, sa.Column('claim_token', sa.String(length=64), nullable=True))
    op.add_column(T, sa.Column('claim_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f('fk_workflow_recovery_actions_approved_by_users'), T, 'users', ['approved_by'], ['id'], ondelete='RESTRICT')
    op.create_foreign_key(op.f('fk_workflow_recovery_actions_rejected_by_users'), T, 'users', ['rejected_by'], ['id'], ondelete='RESTRICT')

    op.create_check_constraint(op.f('ck_workflow_recovery_actions_action_type_valid'), T, ACTIONS)
    op.create_check_constraint(op.f('ck_workflow_recovery_actions_status_valid'), T, STATUSES)
    op.create_index(
        'uq_active_recovery_per_workflow', T, ['workflow_id'], unique=True,
        postgresql_where=sa.text("status IN ('requested', 'approved', 'queued', 'executing')"),
    )
    op.create_index(
        'ix_recovery_stale_lease', T, ['claim_expires_at'],
        postgresql_where=sa.text("status = 'executing'"),
    )

    op.create_table('outbox_messages',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('aggregate_id', sa.UUID(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='pending', nullable=False),
        sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('claim_token', sa.String(length=64), nullable=True),
        sa.Column('claimed_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'published', 'dead')", name=op.f('ck_outbox_messages_status_valid')),
        sa.CheckConstraint('attempts >= 0', name=op.f('ck_outbox_messages_attempts_non_negative')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox_messages')),
    )
    op.create_index('ix_outbox_due', 'outbox_messages', ['next_attempt_at'], unique=False, postgresql_where=sa.text("status = 'pending'"))
    op.create_index('ix_outbox_aggregate', 'outbox_messages', ['aggregate_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_outbox_aggregate', table_name='outbox_messages')
    op.drop_index('ix_outbox_due', table_name='outbox_messages', postgresql_where=sa.text("status = 'pending'"))
    op.drop_table('outbox_messages')

    op.drop_index('ix_recovery_stale_lease', table_name=T, postgresql_where=sa.text("status = 'executing'"))
    op.drop_index('uq_active_recovery_per_workflow', table_name=T,
                  postgresql_where=sa.text("status IN ('requested', 'approved', 'queued', 'executing')"))
    op.drop_constraint(op.f('ck_workflow_recovery_actions_status_valid'), T, type_='check')
    op.drop_constraint(op.f('ck_workflow_recovery_actions_action_type_valid'), T, type_='check')

    # Statuses introduced by this revision have no old equivalent.
    op.execute("UPDATE workflow_recovery_actions SET status = 'approved' WHERE status IN ('queued', 'executing')")
    op.execute(
        "UPDATE workflow_recovery_actions SET action_type = CASE action_type "
        "WHEN 'retry_workflow' THEN 'retry' ELSE 'manual_review' END"
    )

    op.drop_constraint(op.f('fk_workflow_recovery_actions_rejected_by_users'), T, type_='foreignkey')
    op.drop_constraint(op.f('fk_workflow_recovery_actions_approved_by_users'), T, type_='foreignkey')
    for col in ('claim_expires_at', 'claim_token', 'rejected_at', 'approved_at',
                'error_message', 'rejection_reason', 'rejected_by', 'approved_by'):
        op.drop_column(T, col)

    op.alter_column(T, 'reason', existing_type=sa.Text(), nullable=True)
    op.alter_column(T, 'action_type', new_column_name='action')
    op.create_check_constraint(op.f('ck_workflow_recovery_actions_action_valid'), T, OLD_ACTIONS)
    op.create_check_constraint(op.f('ck_workflow_recovery_actions_status_valid'), T, OLD_STATUSES)
