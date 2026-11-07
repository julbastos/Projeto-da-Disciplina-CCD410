"""
DB1 (MongoDB): inicializa o replica set rs0 e cria a coleção de livros
com validação de esquema e índices.
"""
import time
from pymongo import MongoClient, WriteConcern
from pymongo.errors import OperationFailure

HOST = "mongo1:27017"
MEMBERS = ["mongo1:27017", "mongo2:27017", "mongo3:27017"]

client = MongoClient(HOST, directConnection=True, serverSelectionTimeoutMS=10000)

# 1) Inicia o replica set 
config = {
    "_id": "rs0",
    "members": [{"_id": i, "host": h} for i, h in enumerate(MEMBERS)],
}
try:
    client.admin.command("replSetInitiate", config)
    print("Replica set iniciado.")
except OperationFailure as e:
    if e.code == 23:  # AlreadyInitialized
        print("Replica set já estava iniciado.")
    else:
        raise

# 2) Espera a eleição do primário
for _ in range(60):
    if client.admin.command("hello").get("isWritablePrimary"):
        break
    time.sleep(1)
else:
    raise RuntimeError("Primário não foi eleito a tempo.")

db = client["biblioteca"]

# 3) Coleção de livros com esquema flexível (autores e gêneros são listas)
if "livros" not in db.list_collection_names():
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
print("Coleção 'livros' pronta.")
