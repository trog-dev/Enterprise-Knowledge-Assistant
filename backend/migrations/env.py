from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool

from app.db.base import Base
from app.db.session import engine
from app.models import User, Document, DocumentChunk  # Đăng ký bảng users vào Base.metadata
from app.models import Conversation, ConversationTurn

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Migration dùng một kết nối riêng, không cần connection pool.
    migration_engine = engine.execution_options()

    with migration_engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

