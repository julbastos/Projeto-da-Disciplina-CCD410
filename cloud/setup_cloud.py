"""
Cria o esquema do projeto nos três serviços de nuvem:
  - PostgreSQL (Neon)
  - MongoDB (Atlas)
  - Cassandra (DataStax Astra DB)

Pré-requisito no Astra: o keyspace 'biblioteca' já deve existir
(criado pela interface do Astra, pois ele não aceita SimpleStrategy).

Uso:
    pip install -r requirements.txt
    python cloud/setup_cloud.py
"""
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---------- helpers ----------

def ler_sem_comentarios(caminho: Path) -> str:
    linhas = [l for l in caminho.read_text(encoding="utf-8").splitlines()
              if not l.strip().startswith("--")]
    return "\n".join(linhas)

def exigir(var: str) -> str:
    valor = os.getenv(var)
    if not valor or valor.startswith(("USUARIO", "AstraCS:xxx")):
        sys.exit(f"Variável {var} não preenchida no arquivo .env")
    return valor

# ---------- 1. PostgreSQL (Neon) ----------

def setup_postgres():
    import psycopg
    print("[PostgreSQL] criando tabelas...")
    sql = ler_sem_comentarios(ROOT / "db" / "postgres" / "init.sql")
    with psycopg.connect(exigir("POSTGRES_URL"), autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS estoque, usuarios")
        conn.execute(sql)
    print("[PostgreSQL] OK: usuarios e estoque criadas.")

# ---------- 2. MongoDB (Atlas) ----------

def setup_mongo():
    from pymongo import MongoClient, WriteConcern
    print("[MongoDB] criando coleção livros...")
    client = MongoClient(exigir("MONGO_URL"), serverSelectionTimeoutMS=15000)
    db = client["biblioteca"]
    if "livros" in db.list_collection_names():
        db.drop_collection("livros")
    db.create_collection(
        "livros",
        validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["titulo", "autores", "generos"],
                "properties": {
                    "titulo": {"bsonType": "string"},
                    "autores": {"bsonType": "array", "items": {"bsonType": "string"}},
                    "generos": {"bsonType": "array", "items": {"bsonType": "string"}},
                    "isbn": {"bsonType": "string"},
                    "ano": {"bsonType": "int"},
                },
            }
        },
    )
    livros = db.get_collection("livros", write_concern=WriteConcern(w="majority"))
    livros.create_index("isbn", unique=True, sparse=True)
    livros.create_index("generos")
    livros.create_index("autores")
    livros.create_index("titulo")
    print("[MongoDB] OK: coleção livros e índices criados.")

# ---------- 3. Cassandra (Astra DB) ----------

def setup_cassandra():
    from cassandra.auth import PlainTextAuthProvider
    from cassandra.cluster import Cluster

    print("[Cassandra] criando tabelas...")
    bundle = ROOT / exigir("ASTRA_BUNDLE_PATH").removeprefix("./")
    keyspace = os.getenv("ASTRA_KEYSPACE", "biblioteca")

    cluster = Cluster(
        cloud={"secure_connect_bundle": str(bundle)},
        auth_provider=PlainTextAuthProvider("token", exigir("ASTRA_TOKEN")),
    )
    session = cluster.connect(keyspace)

    # Executa só os CREATE TABLE. Keyspace e USE já são feitos pelo Astra.
    texto = ler_sem_comentarios(ROOT / "db" / "cassandra" / "init.cql")
    for comando in texto.split(";"):
        comando = comando.strip()
        if comando.upper().startswith("CREATE TABLE"):
            session.execute(comando)
    cluster.shutdown()
    print("[Cassandra] OK: tabelas de empréstimos criadas.")

# ---------- main ----------

if __name__ == "__main__":
    erros = []
    for nome, funcao in [("PostgreSQL", setup_postgres),
                         ("MongoDB", setup_mongo),
                         ("Cassandra", setup_cassandra)]:
        try:
            funcao()
        except SystemExit:
            raise
        except Exception as e:
            erros.append(nome)
            print(f"[{nome}] ERRO: {e}")
    if erros:
        sys.exit(f"Falhou em: {', '.join(erros)}")
    print("Esquema criado nos três serviços.")
