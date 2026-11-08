from contextlib import contextmanager
from functools import lru_cache
import base64
import re
from tempfile import NamedTemporaryFile

import psycopg
from psycopg.rows import dict_row
from pymongo import MongoClient
from settings import ROOT, SETTINGS


@contextmanager
def postgres():
    with psycopg.connect(SETTINGS.POSTGRES_URL, row_factory=dict_row, connect_timeout=10) as conn:
        yield conn


@lru_cache
def mongo_client():
    return MongoClient(SETTINGS.MONGO_URL, serverSelectionTimeoutMS=10000, timeoutMS=15000)


def livros():
    return mongo_client().biblioteca.livros


@contextmanager
def astra_bundle():
    if not SETTINGS.ASTRA_BUNDLE_BASE64:
        yield str(ROOT / SETTINGS.ASTRA_BUNDLE_PATH)
        return
    # O filesystem da aplicação é somente leitura em funções serverless.
    data = base64.b64decode(SETTINGS.ASTRA_BUNDLE_BASE64, validate=True)
    with NamedTemporaryFile(suffix='.zip', dir='/tmp') as bundle:
        bundle.write(data)
        bundle.flush()
        yield bundle.name


@lru_cache
def cassandra():
    from cassandra.auth import PlainTextAuthProvider
    from cassandra.cluster import Cluster
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', SETTINGS.ASTRA_KEYSPACE):
        raise ValueError('keyspace inválido')
    with astra_bundle() as bundle:
        cluster = Cluster(
            cloud={'secure_connect_bundle': bundle},
            auth_provider=PlainTextAuthProvider('token', SETTINGS.ASTRA_TOKEN),
            connect_timeout=10,
        )
        try:
            return cluster, cluster.connect(SETTINGS.ASTRA_KEYSPACE)
        except Exception:
            cluster.shutdown()
            raise


def fechar_conexoes():
    if mongo_client.cache_info().currsize:
        mongo_client().close()
        mongo_client.cache_clear()
    if cassandra.cache_info().currsize:
        cassandra()[0].shutdown()
        cassandra.cache_clear()
