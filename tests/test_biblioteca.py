import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import UUID
from fastapi.testclient import TestClient
from app import app
import router

LIVRO = '507f1f77bcf86cd799439011'


class Connection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, args=()):
        if 'pg_advisory_xact_lock' in sql:
            return self.conn.execute('SELECT 1')
        return self.conn.execute(sql.replace('%s', '?'), tuple(str(a) if isinstance(a, UUID) else a for a in args))


class BibliotecaTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA foreign_keys=ON;
            CREATE TABLE usuarios(id INTEGER PRIMARY KEY, nome TEXT, email TEXT UNIQUE, telefone TEXT DEFAULT '', matricula TEXT DEFAULT '', criado_em TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE estoque(livro_id TEXT PRIMARY KEY, quantidade INTEGER CHECK(quantidade>=0));
            CREATE TABLE emprestimos(id TEXT PRIMARY KEY, usuario_id INTEGER REFERENCES usuarios(id), livro_id TEXT REFERENCES estoque(livro_id), criado_em TEXT DEFAULT CURRENT_TIMESTAMP, devolvido BOOLEAN DEFAULT false, sincronizado BOOLEAN DEFAULT false);
            INSERT INTO usuarios(nome,email) VALUES ('ana','ana@teste.com');
        ''')
        self.db.execute('INSERT INTO estoque VALUES (?,1)', (LIVRO,))
        self.db.commit()

        @contextmanager
        def postgres():
            with self.db:
                yield Connection(self.db)

        self.patches = [patch.object(router, 'postgres', postgres), patch.object(router, 'livros'), patch.object(router, 'sincronizar', side_effect=RuntimeError('offline'))]
        for p in self.patches:
            p.start()
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.db.close()

    def emprestar(self, usuario_id=1):
        return self.client.post('/api/emprestimos', json={'usuario_id': usuario_id, 'livro_id': LIVRO})

    def test_emprestimo_persistido_quando_cassandra_falha(self):
        response = self.emprestar()
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()['sincronizado'])
        self.assertEqual(self.db.execute('SELECT quantidade FROM estoque').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM emprestimos').fetchone()[0], 1)
        self.assertEqual(self.emprestar().status_code, 409)
        self.assertEqual(self.db.execute('SELECT count(*) FROM emprestimos').fetchone()[0], 1)

    def test_devolucao_repetida_nao_duplica_estoque(self):
        emprestimo = self.emprestar().json()
        self.assertEqual(UUID(emprestimo['id']).version, 1)
        url = '/api/emprestimos/' + emprestimo['id'] + '/devolucao'
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 409)
        self.assertEqual(self.db.execute('SELECT quantidade FROM estoque').fetchone()[0], 1)

    def test_leitor_inexistente_preserva_estoque(self):
        self.assertEqual(self.emprestar(999).status_code, 404)
        self.assertEqual(self.db.execute('SELECT quantidade FROM estoque').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM emprestimos').fetchone()[0], 0)

    def test_validacao_de_entrada(self):
        for data in ({'nome':'a', 'email':'ana@teste.com'}, {'nome':'ana', 'email':'incorreto'}):
            self.assertEqual(self.client.post('/api/usuarios', json=data).status_code, 422)
        self.assertEqual(self.client.post('/api/livros', json={'titulo':'livro','autores':[' '],'generos':['teste']}).status_code, 422)
        self.assertEqual(self.client.put('/api/livros/'+LIVRO+'/estoque', json={'quantidade':-1}).status_code, 422)
        self.assertEqual(self.client.post('/api/emprestimos', json={'usuario_id':1,'livro_id':'inválido'}).status_code, 422)

    def test_interface_e_erro_sanitizado(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertIn('biblioteca plural', self.client.get('/').text)
        self.assertEqual(self.client.get('/static/app.js').status_code, 200)
        response = self.client.post('/api/sincronizar')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('offline', response.text)

    def test_falha_ao_inserir_emprestimo_reverte_retirada(self):
        self.db.execute("CREATE TRIGGER recusar BEFORE INSERT ON emprestimos BEGIN SELECT RAISE(ABORT,'falha'); END")
        self.db.commit()
        self.assertEqual(self.emprestar().status_code, 503)
        self.assertEqual(self.db.execute('SELECT quantidade FROM estoque').fetchone()[0], 1)

    def test_sincronizacao_pode_ser_repetida_apos_falha_parcial(self):
        self.emprestar()
        self.patches[-1].stop()
        with patch.object(router, 'cassandra') as mock:
            session = mock.return_value.__getitem__.return_value
            session.execute.side_effect = [None, RuntimeError('falha parcial')]
            self.assertEqual(self.client.post('/api/sincronizar').status_code, 503)
            self.assertEqual(self.db.execute('SELECT sincronizado FROM emprestimos').fetchone()[0], 0)
            session.execute.side_effect = None
            self.assertEqual(self.client.post('/api/sincronizar').json()['sincronizados'], 1)
            self.assertEqual(self.client.post('/api/sincronizar').json()['sincronizados'], 0)
            self.assertEqual(self.db.execute('SELECT sincronizado FROM emprestimos').fetchone()[0], 1)
