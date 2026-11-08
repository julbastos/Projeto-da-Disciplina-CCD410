from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from database import postgres, livros
from schemas.livros import LivroCriar, EstoqueAtualizar

router = APIRouter(tags=['livros'])


def objeto_id(value):
    if not ObjectId.is_valid(value):
        raise HTTPException(422, 'identificador do livro inválido')
    return ObjectId(value)


@router.get('/livros')
def listar_livros(busca: str = Query(default='', max_length=120)):
    import re
    filtro = {'$or': [{campo: {'$regex': re.escape(busca), '$options': 'i'}} for campo in ('titulo', 'autores', 'generos')]} if busca else {}
    docs = list(livros().find(filtro).sort('titulo', 1).limit(200))
    with postgres() as conn:
        estoque = {row['livro_id']: row['quantidade'] for row in conn.execute('SELECT * FROM estoque')}
    return [{**{k: v for k, v in doc.items() if k != '_id'}, 'id': str(doc['_id']), 'quantidade': estoque.get(str(doc['_id']), 0)} for doc in docs]


@router.post('/livros', status_code=201)
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


@router.put('/livros/{livro_id}/estoque')
def atualizar_estoque(livro_id: str, data: EstoqueAtualizar):
    objeto_id(livro_id)
    with postgres() as conn:
        row = conn.execute('UPDATE estoque SET quantidade=%s WHERE livro_id=%s RETURNING *', (data.quantidade, livro_id)).fetchone()
        if not row:
            raise HTTPException(404, 'livro não encontrado')
        return row


@router.put('/livros/{livro_id}')
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


@router.delete('/livros/{livro_id}')
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
