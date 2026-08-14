"""Add Default profile

Revision ID: 88d1b76b4f68
Revises: 6488d9f00243
Create Date: 2026-08-14 09:00:35.355822

"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column, Uuid, String, DateTime

# revision identifiers, used by Alembic.
revision: str = '88d1b76b4f68'
down_revision: Union[str, Sequence[str], None] = '6488d9f00243'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    now = datetime.now(timezone.utc)
    profile = table(
        'profile',
        column('id', Uuid),
        column('name', String),
        column('city', String),
        column('selected_at', DateTime),
        column('created_at', DateTime),
        column('updated_at', DateTime),
    )
    op.bulk_insert(profile, [
        {
            "id": uuid.uuid4(),
            "name": "Default",
            "city": "Berlin",
            "selected_at": now,
            "created_at": now,
            "updated_at": now,
        }
    ])


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM profile WHERE name = 'Default'")
