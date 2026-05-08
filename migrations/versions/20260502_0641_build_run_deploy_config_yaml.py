"""build_run_deploy_config_yaml

Revision ID: 7b5e46aa8dec
Revises: 3adac58ac0c7
Create Date: 2026-05-02 06:41:59.892922+00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b5e46aa8dec"
down_revision: str | None = "3adac58ac0c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "build_runs",
        sa.Column("deploy_config_yaml", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("build_runs", "deploy_config_yaml")
