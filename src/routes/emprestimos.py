from uuid import UUID, uuid1
from bson import ObjectId
from fastapi import APIRouter, HTTPException
from database import postgres, livros, cassandra
from schemas.emprestimos import EmprestimoCriar, EmprestimoAtualizar
from routes.livros import objeto_id

router = APIRouter(tags=['empréstimos'])


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


@router.get('/emprestimos')
def listar_emprestimos(usuario_id: int | None = None, livro_id: str | None = None):
    with postgres() as conn:
        return conn.execute('''SELECT e.*, u.nome AS usuario_nome FROM emprestimos e
            JOIN usuarios u ON u.id=e.usuario_id
            WHERE (%s::int IS NULL OR e.usuario_id=%s) AND (%s::text IS NULL OR e.livro_id=%s)
            ORDER BY e.criado_em DESC LIMIT 200''', (usuario_id, usuario_id, livro_id, livro_id)).fetchall()


@router.post('/emprestimos', status_code=201)
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


@router.put('/emprestimos/{emprestimo_id}')
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


@router.post('/emprestimos/{emprestimo_id}/devolucao')
def devolver(emprestimo_id: UUID):
    return atualizar_emprestimo(emprestimo_id, EmprestimoAtualizar(devolvido=True))


@router.post('/sincronizar')
def sincronizar_historico():
    try:
        return {'sincronizados': sincronizar()}
    except Exception:
        raise HTTPException(503, 'cassandra indisponível; os registros continuam pendentes no postgres')


@router.get('/historico/usuarios/{usuario_id}')
def historico_usuario(usuario_id: int):
    rows = cassandra()[1].execute('SELECT * FROM emprestimos_por_usuario WHERE usuario_id=%s LIMIT 200', (usuario_id,))
    return [row._asdict() for row in rows]


@router.get('/historico/livros/{livro_id}')
def historico_livro(livro_id: str):
    objeto_id(livro_id)
    rows = cassandra()[1].execute('SELECT * FROM emprestimos_por_livro WHERE livro_id=%s LIMIT 200', (livro_id,))
    return [row._asdict() for row in rows]


@router.delete('/emprestimos/{emprestimo_id}')
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
