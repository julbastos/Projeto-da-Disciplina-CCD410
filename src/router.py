from uuid import UUID, uuid1
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.errors import UniqueViolation, ForeignKeyViolation
from database import postgres, livros, cassandra
from schemas.usuarios import Usuario, UsuarioCriar
from schemas.livros import LivroCriar, EstoqueAtualizar

main_router = APIRouter(prefix='/api')
leitores_router = APIRouter(tags=['leitores'])
livros_router = APIRouter(tags=['livros'])
emprestimos_router = APIRouter(tags=['empréstimos'])


class EmprestimoAtualizar(BaseModel):
    devolvido: bool


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
        exclusoes = conn.execute('SELECT * FROM emprestimos_excluidos LIMIT 100').fetchall()
        if not rows and not exclusoes:
            return 0
        session = cassandra()[1]
        usuario = session.prepare('INSERT INTO emprestimos_por_usuario (usuario_id, emprestimo_em, livro_id, devolvido) VALUES (?, ?, ?, ?)')
        livro = session.prepare('INSERT INTO emprestimos_por_livro (livro_id, emprestimo_em, usuario_id, devolvido) VALUES (?, ?, ?, ?)')
        for row in rows:
            session.execute(usuario, (row['usuario_id'], row['id'], row['livro_id'], row['devolvido']))
            session.execute(livro, (row['livro_id'], row['id'], row['usuario_id'], row['devolvido']))
            conn.execute('UPDATE emprestimos SET sincronizado=true WHERE id=%s', (row['id'],))
        excluir_usuario = session.prepare('DELETE FROM emprestimos_por_usuario WHERE usuario_id=? AND emprestimo_em=?')
        excluir_livro = session.prepare('DELETE FROM emprestimos_por_livro WHERE livro_id=? AND emprestimo_em=?')
        for row in exclusoes:
            session.execute(excluir_usuario, (row['usuario_id'], row['id']))
            session.execute(excluir_livro, (row['livro_id'], row['id']))
            conn.execute('DELETE FROM emprestimos_excluidos WHERE id=%s', (row['id'],))
        return len(rows) + len(exclusoes)


def tentar_sincronizar():
    try:
        sincronizar()
        return True
    except Exception:
        return False


@leitores_router.get('/usuarios', response_model=list[Usuario])
def listar_usuarios():
    with postgres() as conn:
        return conn.execute('SELECT * FROM usuarios ORDER BY nome').fetchall()


@leitores_router.post('/usuarios', response_model=Usuario, status_code=201)
def criar_usuario(data: UsuarioCriar):
    try:
        with postgres() as conn:
            return conn.execute('INSERT INTO usuarios (nome,email,telefone,matricula) VALUES (%s,%s,%s,%s) RETURNING *',
                                (data.nome, data.email, data.telefone, data.matricula)).fetchone()
    except UniqueViolation:
        raise HTTPException(409, 'email já cadastrado')


@livros_router.get('/livros')
def listar_livros(busca: str = Query(default='', max_length=120)):
    import re
    filtro = {'$or': [{campo: {'$regex': re.escape(busca), '$options': 'i'}} for campo in ('titulo', 'autores', 'generos')]} if busca else {}
    docs = list(livros().find(filtro).sort('titulo', 1).limit(200))
    with postgres() as conn:
        estoque = {row['livro_id']: row['quantidade'] for row in conn.execute('SELECT * FROM estoque')}
    return [{**{k: v for k, v in doc.items() if k != '_id'}, 'id': str(doc['_id']), 'quantidade': estoque.get(str(doc['_id']), 0)} for doc in docs]


@livros_router.post('/livros', status_code=201)
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


@livros_router.put('/livros/{livro_id}/estoque')
def atualizar_estoque(livro_id: str, data: EstoqueAtualizar):
    objeto_id(livro_id)
    with postgres() as conn:
        row = conn.execute('UPDATE estoque SET quantidade=%s WHERE livro_id=%s RETURNING *', (data.quantidade, livro_id)).fetchone()
        if not row:
            raise HTTPException(404, 'livro não encontrado')
        return row


@emprestimos_router.get('/emprestimos')
def listar_emprestimos(usuario_id: int | None = None, livro_id: str | None = None):
    with postgres() as conn:
        return conn.execute('''SELECT e.*, u.nome AS usuario_nome FROM emprestimos e
            JOIN usuarios u ON u.id=e.usuario_id
            WHERE (%s::int IS NULL OR e.usuario_id=%s) AND (%s::text IS NULL OR e.livro_id=%s)
            ORDER BY e.criado_em DESC LIMIT 200''', (usuario_id, usuario_id, livro_id, livro_id)).fetchall()


@emprestimos_router.post('/emprestimos', status_code=201)
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


@emprestimos_router.put('/emprestimos/{emprestimo_id}')
def atualizar_emprestimo(emprestimo_id: UUID, data: EmprestimoAtualizar):
    with postgres() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(410)')
        row = conn.execute('SELECT * FROM emprestimos WHERE id=%s FOR UPDATE', (emprestimo_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'empréstimo não encontrado')
        if bool(row['devolvido']) == data.devolvido:
            raise HTTPException(409, 'o empréstimo já está nessa situação')
        if data.devolvido:
            conn.execute('UPDATE estoque SET quantidade=quantidade+1 WHERE livro_id=%s', (row['livro_id'],))
        else:
            estoque = conn.execute('UPDATE estoque SET quantidade=quantidade-1 WHERE livro_id=%s AND quantidade>0 RETURNING *', (row['livro_id'],)).fetchone()
            if not estoque:
                raise HTTPException(409, 'livro sem exemplares disponíveis')
        row = conn.execute('UPDATE emprestimos SET devolvido=%s, sincronizado=false WHERE id=%s RETURNING *',
                           (data.devolvido, emprestimo_id)).fetchone()
    tentar_sincronizar()
    return row


@emprestimos_router.post('/emprestimos/{emprestimo_id}/devolucao')
def devolver(emprestimo_id: UUID):
    return atualizar_emprestimo(emprestimo_id, EmprestimoAtualizar(devolvido=True))


@emprestimos_router.post('/sincronizar')
def sincronizar_historico():
    try:
        return {'sincronizados': sincronizar()}
    except Exception:
        raise HTTPException(503, 'cassandra indisponível; os registros continuam pendentes no postgres')


@emprestimos_router.get('/historico/usuarios/{usuario_id}')
def historico_usuario(usuario_id: int):
    rows = cassandra()[1].execute('SELECT * FROM emprestimos_por_usuario WHERE usuario_id=%s LIMIT 200', (usuario_id,))
    return [row._asdict() for row in rows]


@emprestimos_router.get('/historico/livros/{livro_id}')
def historico_livro(livro_id: str):
    objeto_id(livro_id)
    rows = cassandra()[1].execute('SELECT * FROM emprestimos_por_livro WHERE livro_id=%s LIMIT 200', (livro_id,))
    return [row._asdict() for row in rows]


@leitores_router.put('/usuarios/{usuario_id}', response_model=Usuario)
def editar_usuario(usuario_id: int, data: UsuarioCriar):
    try:
        with postgres() as conn:
            row = conn.execute(
                'UPDATE usuarios SET nome=%s,email=%s,telefone=%s,matricula=%s WHERE id=%s RETURNING *',
                (data.nome, data.email, data.telefone, data.matricula, usuario_id),
            ).fetchone()
            if not row:
                raise HTTPException(404, 'leitor não encontrado')
            return row
    except UniqueViolation:
        raise HTTPException(409, 'email já cadastrado')


@leitores_router.delete('/usuarios/{usuario_id}')
def excluir_usuario(usuario_id: int):
    try:
        with postgres() as conn:
            if conn.execute('SELECT id FROM emprestimos WHERE usuario_id=%s LIMIT 1', (usuario_id,)).fetchone():
                raise HTTPException(409, 'exclua os empréstimos deste leitor antes de excluir o cadastro')
            row = conn.execute('DELETE FROM usuarios WHERE id=%s RETURNING id', (usuario_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'leitor não encontrado')
    except ForeignKeyViolation:
        raise HTTPException(409, 'exclua os empréstimos deste leitor antes de excluir o cadastro')
    return {'detail': 'leitor excluído'}


@livros_router.put('/livros/{livro_id}')
def editar_livro(livro_id: str, data: LivroCriar):
    from pymongo.errors import DuplicateKeyError
    oid = objeto_id(livro_id)
    # o lock do estoque também serializa edições e exclusões deste livro.
    with postgres() as conn:
        row = conn.execute('SELECT * FROM estoque WHERE livro_id=%s FOR UPDATE', (livro_id,)).fetchone()
        if not row or not livros().find_one({'_id': oid}):
            raise HTTPException(404, 'livro não encontrado')
        doc = data.model_dump(exclude={'quantidade'}, exclude_none=True)
        if not doc.get('isbn'):
            doc.pop('isbn', None)
        try:
            livros().replace_one({'_id': oid}, doc)
        except DuplicateKeyError:
            raise HTTPException(409, 'isbn já cadastrado')
        conn.execute('UPDATE estoque SET quantidade=%s WHERE livro_id=%s', (data.quantidade, livro_id))
    return {'id': livro_id, **data.model_dump()}


@livros_router.delete('/livros/{livro_id}')
def excluir_livro(livro_id: str):
    oid = objeto_id(livro_id)
    with postgres() as conn:
        row = conn.execute('SELECT * FROM estoque WHERE livro_id=%s FOR UPDATE', (livro_id,)).fetchone()
        if not row or not livros().find_one({'_id': oid}):
            raise HTTPException(404, 'livro não encontrado')
        if conn.execute('SELECT id FROM emprestimos WHERE livro_id=%s LIMIT 1', (livro_id,)).fetchone():
            raise HTTPException(409, 'exclua os empréstimos deste livro antes de excluir o cadastro')
        livros().delete_one({'_id': oid})
        conn.execute('DELETE FROM estoque WHERE livro_id=%s', (livro_id,))
    return {'detail': 'livro excluído'}


@emprestimos_router.delete('/emprestimos/{emprestimo_id}')
def excluir_emprestimo(emprestimo_id: UUID):
    with postgres() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(410)')
        row = conn.execute('DELETE FROM emprestimos WHERE id=%s RETURNING *', (emprestimo_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'empréstimo não encontrado')
        if not row['devolvido']:
            conn.execute('UPDATE estoque SET quantidade=quantidade+1 WHERE livro_id=%s', (row['livro_id'],))
        # preserva as chaves para remover as duas cópias do cassandra mesmo offline.
        conn.execute('INSERT INTO emprestimos_excluidos (id,usuario_id,livro_id) VALUES (%s,%s,%s)',
                     (emprestimo_id, row['usuario_id'], row['livro_id']))
    tentar_sincronizar()
    return {'detail': 'empréstimo excluído'}

main_router.include_router(leitores_router)
main_router.include_router(livros_router)
main_router.include_router(emprestimos_router)
