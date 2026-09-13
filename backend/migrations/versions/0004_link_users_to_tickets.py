"""Link users and workers to tickets.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE tickets
        ADD COLUMN created_by_id INTEGER NULL
    """)
    op.execute("""
        ALTER TABLE tickets
        ADD CONSTRAINT fk_tickets_created_by_id_users
        FOREIGN KEY (created_by_id) REFERENCES users (id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX ix_tickets_created_by_id ON tickets (created_by_id)")

    op.execute("""
        CREATE TABLE ticket_assignments (
            ticket_id INTEGER NOT NULL,
            worker_id INTEGER NOT NULL,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT pk_ticket_assignments PRIMARY KEY (ticket_id, worker_id),
            CONSTRAINT fk_ticket_assignments_ticket_id_tickets
                FOREIGN KEY (ticket_id) REFERENCES tickets (id) ON DELETE CASCADE,
            CONSTRAINT fk_ticket_assignments_worker_id_workers
                FOREIGN KEY (worker_id) REFERENCES workers (user_id) ON DELETE CASCADE
        )
    """)
    op.execute(
        "CREATE INDEX ix_ticket_assignments_worker_id ON ticket_assignments (worker_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ticket_assignments")
    op.execute("DROP INDEX ix_tickets_created_by_id")
    op.execute("ALTER TABLE tickets DROP CONSTRAINT fk_tickets_created_by_id_users")
    op.execute("ALTER TABLE tickets DROP COLUMN created_by_id")
