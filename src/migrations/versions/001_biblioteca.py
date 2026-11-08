"""cria a estrutura relacional sem apagar registros existentes"""
from alembic import op
from settings import ROOT

revision = '001_biblioteca'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    for arquivo in ('init.sql', 'aplicacao.sql'):
        op.execute((ROOT / 'db' / 'postgres' / arquivo).read_text())


def downgrade():
    raise RuntimeError('reversão automática desabilitada para preservar os dados da biblioteca')
