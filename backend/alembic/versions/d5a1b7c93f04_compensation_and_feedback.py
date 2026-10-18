"""compensation (release reservation) and investigation feedback

Revision ID: d5a1b7c93f04
Revises: c3d9f1a05e72
Create Date: 2026-10-21 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd5a1b7c93f04'
down_revision: Union[str, Sequence[str], None] = 'c3d9f1a05e72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORDER_NEW = "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')"
ORDER_OLD = "status IN ('pending', 'processing', 'completed', 'failed')"
WORKFLOW_NEW = ("status IN ('pending', 'processing', 'retry_scheduled', 'failed', "
                "'needs_review', 'completed', 'compensated')")
WORKFLOW_OLD = ("status IN ('pending', 'processing', 'retry_scheduled', 'failed', "
                "'needs_review', 'completed')")
ACTION_NEW = ("action_type IN ('retry_workflow', 'reconcile_and_resume', "
              "'mark_for_review', 'release_reservation')")
ACTION_OLD = "action_type IN ('retry_workflow', 'reconcile_and_resume', 'mark_for_review')"
RECOMMENDED_NEW = ("recommended_action IS NULL OR recommended_action IN ('retry_workflow', "
                   "'reconcile_and_resume', 'mark_for_review', 'release_reservation', 'no_action')")
RECOMMENDED_OLD = ("recommended_action IS NULL OR recommended_action IN ('retry_workflow', "
                   "'reconcile_and_resume', 'mark_for_review', 'no_action')")


def _swap(table: str, name: str, new_condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_='check')
    op.create_check_constraint(op.f(name), table, new_condition)


def upgrade() -> None:
    _swap('orders', 'ck_orders_status_valid', ORDER_NEW)
    _swap('workflows', 'ck_workflows_status_valid', WORKFLOW_NEW)
    _swap('workflow_recovery_actions', 'ck_workflow_recovery_actions_action_type_valid', ACTION_NEW)
    _swap('investigations', 'ck_investigations_recommended_action_valid', RECOMMENDED_NEW)

    op.create_table('investigation_feedback',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('investigation_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('rating', sa.String(length=20), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("rating IN ('helpful', 'not_helpful')", name=op.f('ck_investigation_feedback_rating_valid')),
        sa.ForeignKeyConstraint(['investigation_id'], ['investigations.id'], name=op.f('fk_investigation_feedback_investigation_id_investigations'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_investigation_feedback_user_id_users'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_investigation_feedback')),
        sa.UniqueConstraint('investigation_id', 'user_id', name='uq_feedback_investigation_user'),
    )
    op.create_index('ix_feedback_investigation', 'investigation_feedback', ['investigation_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_feedback_investigation', table_name='investigation_feedback')
    op.drop_table('investigation_feedback')

    # Values introduced here have no older equivalent.
    op.execute("UPDATE investigations SET recommended_action = 'mark_for_review' WHERE recommended_action = 'release_reservation'")
    op.execute("UPDATE workflow_recovery_actions SET action_type = 'mark_for_review' WHERE action_type = 'release_reservation'")
    op.execute("UPDATE workflows SET status = 'failed' WHERE status = 'compensated'")
    op.execute("UPDATE orders SET status = 'failed' WHERE status = 'cancelled'")

    _swap('investigations', 'ck_investigations_recommended_action_valid', RECOMMENDED_OLD)
    _swap('workflow_recovery_actions', 'ck_workflow_recovery_actions_action_type_valid', ACTION_OLD)
    _swap('workflows', 'ck_workflows_status_valid', WORKFLOW_OLD)
    _swap('orders', 'ck_orders_status_valid', ORDER_OLD)
