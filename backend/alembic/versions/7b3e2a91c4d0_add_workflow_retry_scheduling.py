"""add workflow retry scheduling

Revision ID: 7b3e2a91c4d0
Revises: 4d9611405042
Create Date: 2026-10-18 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7b3e2a91c4d0'
down_revision: Union[str, Sequence[str], None] = '4d9611405042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "status IN ('pending', 'processing', 'failed', 'needs_review', 'completed')"
NEW = "status IN ('pending', 'processing', 'retry_scheduled', 'failed', 'needs_review', 'completed')"


def upgrade() -> None:
    op.add_column('workflows', sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(op.f('ck_workflows_status_valid'), 'workflows', type_='check')
    op.create_check_constraint(op.f('ck_workflows_status_valid'), 'workflows', NEW)
    # now() is frozen per transaction, so events written together tied.
    op.alter_column('workflow_events', 'created_at', server_default=sa.text('clock_timestamp()'))
    op.create_index(
        'ix_workflow_retry_due', 'workflows', ['next_retry_at'],
        postgresql_where=sa.text("status = 'retry_scheduled'"),
    )


def downgrade() -> None:
    # Retry-scheduled rows have no equivalent in the old schema.
    op.execute("UPDATE workflows SET status = 'processing' WHERE status = 'retry_scheduled'")
    op.alter_column('workflow_events', 'created_at', server_default=sa.text('now()'))
    op.drop_index('ix_workflow_retry_due', table_name='workflows')
    op.drop_constraint(op.f('ck_workflows_status_valid'), 'workflows', type_='check')
    op.create_check_constraint(op.f('ck_workflows_status_valid'), 'workflows', OLD)
    op.drop_column('workflows', 'next_retry_at')
