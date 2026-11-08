from uuid import UUID, uuid1
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.errors import UniqueViolation
from database import postgres, livros, cassandra
from schemas.usuarios import Usuario, UsuarioCriar
from schemas.livros import LivroCriar, EstoqueAtualizar

main_router = APIRouter(prefix='/api')


class EmprestimoCriar(BaseModel):
    usuario_id: int = Field(gt=0)
    livro_id: str


def objeto_id(value):
    if not ObjectId.is_valid(value):
        raise HTTPException(422, 'identificador do livro inválido')
    return ObjectId(value)


def sincronizar():
    # lock de transação impede que uma projeção antiga sobrescreva uma devolução.
    with postgres() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(410)')
        rows = conn.execute('SELECT * FROM emprestimos WHERE NOT sincronizado ORDER BY criado_em LIMIT 100').fetchall()
        if not rows:
            return 0
        session = cassandra()[1]
        usuario = session.prepare('INSERT INTO emprestimos_por_usuario (usuario_id, emprestimo_em, livro_id, devolvido) VALUES (?, ?, ?, ?)')
        livro = session.prepare('INSERT INTO emprestimos_por_livro (livro_id, emprestimo_em, usuario_id, devolvido) VALUES (?, ?, ?, ?)')
        for row in rows:
            session.execute(usuario, (row['usuario_id'], row['id'], row['livro_id'], row['devolvido']))
            session.execute(livro, (row['livro_id'], row['id'], row['usuario_id'], row['devolvido']))
            conn.execute('UPDATE emprestimos SET sincronizado=true WHERE id=%s', (row['id'],))
        return len(rows)


def tentar_sincronizar():
    try:
        sincronizar()
        return True
    except Exception:
        return False


@main_router.get('/usuarios', response_model=list[Usuario])
def listar_usuarios():
    with postgres() as conn:
        return conn.execute('SELECT * FROM usuarios ORDER BY nome').fetchall()


@main_router.post('/usuarios', response_model=Usuario, status_code=201)
def criar_usuario(data: UsuarioCriar):
    try:
        with postgres() as conn:
            return conn.execute('INSERT INTO usuarios (nome,email,telefone,matricula) VALUES (%s,%s,%s,%s) RETURNING *',
                                (data.nome, data.email, data.telefone, data.matricula)).fetchone()
    except UniqueViolation:
        raise HTTPException(409, 'email já cadastrado')


@main_router.get('/livros')
def listar_livros(busca: str = Query(default='', max_length=120)):
    import re
    filtro = {'$or': [{campo: {'$regex': re.escape(busca), '$options': 'i'}} for campo in ('titulo', 'autores', 'generos')]} if busca else {}
    docs = list(livros().find(filtro).sort('titulo', 1).limit(200))
    with postgres() as conn:
        estoque = {row['livro_id']: row['quantidade'] for row in conn.execute('SELECT * FROM estoque')}
    return [{**{k: v for k, v in doc.items() if k != '_id'}, 'id': str(doc['_id']), 'quantidade': estoque.get(str(doc['_id']), 0)} for doc in docs]


@main_router.post('/livros', status_code=201)
def criar_livro(data: LivroCriar):
    from pymongo.errors import DuplicateKeyError
    doc = data.model_dump(exclude={'quantidade'}, exclude_none=True)
    if not doc.get('isbn'):
        doc.pop('isbn', None)
    try:
        result = livros().insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, 'isbn já cadastrado')
    try:
        with postgres() as conn:
            conn.execute('INSERT INTO estoque (livro_id,quantidade) VALUES (%s,%s)', (str(result.inserted_id), data.quantidade))
    except Exception:
        livros().delete_one({'_id': result.inserted_id})
        raise
    return {'id': str(result.inserted_id), **data.model_dump()}


@main_router.put('/livros/{livro_id}/estoque')
def atualizar_estoque(livro_id: str, data: EstoqueAtualizar):
    objeto_id(livro_id)
    with postgres() as conn:
        row = conn.execute('UPDATE estoque SET quantidade=%s WHERE livro_id=%s RETURNING *', (data.quantidade, livro_id)).fetchone()
        if not row:
            raise HTTPException(404, 'livro não encontrado')
        return row


@main_router.get('/emprestimos')
def listar_emprestimos(usuario_id: int | None = None, livro_id: str | None = None):
    with postgres() as conn:
        return conn.execute('''SELECT e.*, u.nome AS usuario_nome FROM emprestimos e
            JOIN usuarios u ON u.id=e.usuario_id
            WHERE (%s::int IS NULL OR e.usuario_id=%s) AND (%s::text IS NULL OR e.livro_id=%s)
            ORDER BY e.criado_em DESC LIMIT 200''', (usuario_id, usuario_id, livro_id, livro_id)).fetchall()


@main_router.post('/emprestimos', status_code=201)
def emprestar(data: EmprestimoCriar):
    objeto_id(data.livro_id)
    if not livros().find_one({'_id': ObjectId(data.livro_id)}):
        raise HTTPException(404, 'livro não encontrado')
    with postgres() as conn:
        if not conn.execute('SELECT id FROM usuarios WHERE id=%s', (data.usuario_id,)).fetchone():
            raise HTTPException(404, 'usuário não encontrado')
        row = conn.execute('UPDATE estoque SET quantidade=quantidade-1 WHERE livro_id=%s AND quantidade>0 RETURNING *', (data.livro_id,)).fetchone()
        if not row:
            raise HTTPException(409, 'livro sem exemplares disponíveis')
        row = conn.execute('INSERT INTO emprestimos (id,usuario_id,livro_id) VALUES (%s,%s,%s) RETURNING *', (uuid1(), data.usuario_id, data.livro_id)).fetchone()
    tentar_sincronizar()
    return row


@main_router.post('/emprestimos/{emprestimo_id}/devolucao')
def devolver(emprestimo_id: UUID):
    with postgres() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(410)')
        row = conn.execute('UPDATE emprestimos SET devolvido=true, sincronizado=false WHERE id=%s AND NOT devolvido RETURNING *', (emprestimo_id,)).fetchone()
        if not row:
            raise HTTPException(409, 'empréstimo inexistente ou já devolvido')
        conn.execute('UPDATE estoque SET quantidade=quantidade+1 WHERE livro_id=%s', (row['livro_id'],))
    tentar_sincronizar()
    return row


@main_router.post('/sincronizar')
def sincronizar_historico():
    try:
        return {'sincronizados': sincronizar()}
    except Exception:
        raise HTTPException(503, 'cassandra indisponível; os registros continuam pendentes no postgres')


@main_router.get('/historico/usuarios/{usuario_id}')
def historico_usuario(usuario_id: int):
    rows = cassandra()[1].execute('SELECT * FROM emprestimos_por_usuario WHERE usuario_id=%s LIMIT 200', (usuario_id,))
    return [row._asdict() for row in rows]


@main_router.get('/historico/livros/{livro_id}')
def historico_livro(livro_id: str):
    objeto_id(livro_id)
    rows = cassandra()[1].execute('SELECT * FROM emprestimos_por_livro WHERE livro_id=%s LIMIT 200', (livro_id,))
    return [row._asdict() for row in rows]


@main_router.get('/saude')
def saude():
    resultado = {}
    for nome, check in (
        ('postgres', lambda: checar_postgres()),
        ('mongodb', lambda: livros().database.command('ping')),
        ('cassandra', lambda: cassandra()[1].execute('SELECT release_version FROM system.local')),
    ):
        try:
            check()
            resultado[nome] = 'conectado'
        except Exception:
            resultado[nome] = 'indisponível'
    return resultado


def checar_postgres():
    with postgres() as conn:
        conn.execute('SELECT 1')
