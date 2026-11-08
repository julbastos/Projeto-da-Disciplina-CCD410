from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool
from settings import SETTINGS

url = make_url(SETTINGS.POSTGRES_URL).set(drivername='postgresql+psycopg')
if context.is_offline_mode():
    context.configure(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with create_engine(url, poolclass=NullPool).connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
