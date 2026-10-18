"""store ai investigation results

Revision ID: c3d9f1a05e72
Revises: a1c4e8f27b60
Create Date: 2026-10-20 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d9f1a05e72'
down_revision: Union[str, Sequence[str], None] = 'a1c4e8f27b60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

T = 'investigations'
STATUSES = "status IN ('pending', 'running', 'completed', 'failed')"
ACTIONS = ("recommended_action IS NULL OR recommended_action IN "
           "('retry_workflow', 'reconcile_and_resume', 'mark_for_review', 'no_action')")
OLD_STATUSES = "status IN ('pending', 'completed', 'failed')"
OLD_ACTIONS = ("recommended_action IS NULL OR recommended_action IN "
               "('retry', 'manual_review', 'no_action')")


def upgrade() -> None:
    op.drop_constraint(op.f('ck_investigations_status_valid'), T, type_='check')
    op.drop_constraint(op.f('ck_investigations_recommended_action_valid'), T, type_='check')
    op.execute(
        "UPDATE investigations SET recommended_action = CASE recommended_action "
        "WHEN 'retry' THEN 'retry_workflow' WHEN 'manual_review' THEN 'mark_for_review' "
        "ELSE recommended_action END"
    )

    op.add_column(T, sa.Column('confidence', sa.Float(), nullable=True))
    op.add_column(T, sa.Column('policy_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(T, sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column(T, sa.Column('prompt_tokens', sa.Integer(), nullable=True))
    op.add_column(T, sa.Column('completion_tokens', sa.Integer(), nullable=True))
    op.add_column(T, sa.Column('latency_ms', sa.Integer(), nullable=True))

    op.create_check_constraint(op.f('ck_investigations_status_valid'), T, STATUSES)
    op.create_check_constraint(op.f('ck_investigations_recommended_action_valid'), T, ACTIONS)
    op.create_check_constraint(
        op.f('ck_investigations_confidence_range'), T,
        'confidence IS NULL OR (confidence >= 0 AND confidence <= 1)',
    )
    op.create_index(
        'uq_active_investigation_per_workflow', T, ['workflow_id'], unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )


def downgrade() -> None:
    op.drop_index('uq_active_investigation_per_workflow', table_name=T,
                  postgresql_where=sa.text("status IN ('pending', 'running')"))
    op.drop_constraint(op.f('ck_investigations_confidence_range'), T, type_='check')
    op.drop_constraint(op.f('ck_investigations_recommended_action_valid'), T, type_='check')
    op.drop_constraint(op.f('ck_investigations_status_valid'), T, type_='check')

    op.execute("UPDATE investigations SET status = 'pending' WHERE status = 'running'")
    op.execute(
        "UPDATE investigations SET recommended_action = CASE recommended_action "
        "WHEN 'retry_workflow' THEN 'retry' ELSE 'manual_review' END "
        "WHERE recommended_action IS NOT NULL AND recommended_action <> 'no_action'"
    )

    for col in ('latency_ms', 'completion_tokens', 'prompt_tokens',
                'error_message', 'policy_result', 'confidence'):
        op.drop_column(T, col)

    op.create_check_constraint(op.f('ck_investigations_status_valid'), T, OLD_STATUSES)
    op.create_check_constraint(op.f('ck_investigations_recommended_action_valid'), T, OLD_ACTIONS)
