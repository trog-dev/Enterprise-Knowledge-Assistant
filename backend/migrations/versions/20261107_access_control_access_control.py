"""Template only; create_access_migration.py sets the actual parent revision."""
from alembic import op
import sqlalchemy as sa

revision = "20261107_access_control"
down_revision = '8659683707b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(150), nullable=False),
    )
    op.add_column("users", sa.Column("department_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_department_id_departments", "users", "departments",
        ["department_id"], ["id"],
    )
    op.create_index("ix_users_department_id", "users", ["department_id"])
    op.add_column("documents", sa.Column(
        "access_scope", sa.String(20), nullable=False,
        server_default=sa.text("'admin_only'"),
    ))
    op.add_column("documents", sa.Column("department_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_documents_department_id_departments", "documents", "departments",
        ["department_id"], ["id"],
    )
    op.create_index("ix_documents_department_id", "documents", ["department_id"])
    op.create_check_constraint(
        "ck_documents_access_scope", "documents",
        "access_scope IN ('admin_only', 'company', 'department')",
    )
    op.create_check_constraint(
        "ck_documents_scope_department", "documents",
        "(access_scope = 'department' AND department_id IS NOT NULL) OR "
        "(access_scope <> 'department' AND department_id IS NULL)",
    )


def downgrade():
    # Removes ACL settings. Application must also be rolled back before use.
    op.drop_constraint("ck_documents_scope_department", "documents", type_="check")
    op.drop_constraint("ck_documents_access_scope", "documents", type_="check")
    op.drop_index("ix_documents_department_id", table_name="documents")
    op.drop_constraint("fk_documents_department_id_departments", "documents", type_="foreignkey")
    op.drop_column("documents", "department_id")
    op.drop_column("documents", "access_scope")
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_constraint("fk_users_department_id_departments", "users", type_="foreignkey")
    op.drop_column("users", "department_id")
    op.drop_table("departments")
