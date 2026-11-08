from fastapi import APIRouter, HTTPException
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from database import postgres
from schemas.usuarios import Usuario, UsuarioCriar

router = APIRouter(tags=['leitores'])


@router.get('/usuarios', response_model=list[Usuario])
def listar_usuarios():
    with postgres() as conn:
        return conn.execute('SELECT * FROM usuarios ORDER BY nome').fetchall()


@router.post('/usuarios', response_model=Usuario, status_code=201)
def criar_usuario(data: UsuarioCriar):
    try:
        with postgres() as conn:
            return conn.execute('INSERT INTO usuarios (nome,email,telefone,matricula) VALUES (%s,%s,%s,%s) RETURNING *',
                                (data.nome, data.email, data.telefone, data.matricula)).fetchone()
    except UniqueViolation:
        raise HTTPException(409, 'email já cadastrado')


@router.put('/usuarios/{usuario_id}', response_model=Usuario)
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


@router.delete('/usuarios/{usuario_id}')
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
