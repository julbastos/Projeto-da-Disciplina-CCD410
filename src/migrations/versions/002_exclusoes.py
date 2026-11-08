"""registra exclusões pendentes no cassandra"""
from alembic import op
from settings import ROOT

revision = '002_exclusoes'
down_revision = '001_biblioteca'
branch_labels = None
depends_on = None


def upgrade():
    op.execute((ROOT / 'db' / 'postgres' / 'exclusoes.sql').read_text())


def downgrade():
    raise RuntimeError('reversão automática desabilitada para preservar exclusões pendentes')
