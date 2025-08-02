from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
import os

# Add the app directory to the path so we can import models
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Import your models and Base
from app.db import Base
from app.models import Account, Analysis, Report, Config  # Import all models

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

def get_url():
    return os.environ.get("DATABASE_URL")

def run_migrations_offline():
    url = get_url()
    context.configure(url=url, target_metadata=target_metadata,
                      literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix='sqlalchemy.',
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection,
                          target_metadata=target_metadata,
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
