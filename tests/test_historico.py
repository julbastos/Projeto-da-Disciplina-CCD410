import unittest
from collections import namedtuple
from unittest.mock import MagicMock, patch
from uuid import uuid1

from fastapi.testclient import TestClient

from app import app
from routes import emprestimos


LIVRO = '507f1f77bcf86cd799439011'
Registro = namedtuple('Registro', 'usuario_id emprestimo_em livro_id devolvido')


class HistoricoTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.session = MagicMock()
        self.patch = patch.object(emprestimos, 'cassandra', return_value=(None, self.session))
        self.cassandra = self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_consultas_serializam_uuid_e_preservam_ordem(self):
        antigo, recente = uuid1(), uuid1()
        registros = [Registro(1, recente, LIVRO, False), Registro(1, antigo, LIVRO, True)]
        for recurso, identificador, tabela, chave, valor in (
            ('usuarios', '1', 'emprestimos_por_usuario', 'usuario_id', 1),
            ('livros', LIVRO, 'emprestimos_por_livro', 'livro_id', LIVRO),
        ):
            with self.subTest(recurso=recurso):
                self.session.execute.return_value = iter(registros)
                response = self.client.get(f'/api/historico/{recurso}/{identificador}')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [dict(r._asdict(), emprestimo_em=str(r.emprestimo_em)) for r in registros])
                self.session.execute.assert_called_with(
                    f'SELECT * FROM {tabela} WHERE {chave}=%s LIMIT 200', (valor,))

    def test_historico_vazio(self):
        self.session.execute.return_value = []
        for path in ('usuarios/1', 'livros/' + LIVRO):
            with self.subTest(path=path):
                response = self.client.get('/api/historico/' + path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])

    def test_livro_em_maiusculas_usa_chave_canonica(self):
        self.session.execute.return_value = []
        response = self.client.get('/api/historico/livros/' + LIVRO.upper())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.session.execute.call_args.args[1], (LIVRO,))

    def test_identificadores_invalidos_nao_consultam_cassandra(self):
        for path in ('usuarios/abc', 'usuarios/0', 'usuarios/-1', 'usuarios/2147483648', 'livros/invalido'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get('/api/historico/' + path).status_code, 422)
        self.cassandra.assert_not_called()

    def test_falhas_na_conexao_consulta_e_paginacao_retornam_503(self):
        def paginas():
            yield Registro(1, uuid1(), LIVRO, False)
            raise RuntimeError('detalhe privado')

        for path in ('usuarios/1', 'livros/' + LIVRO):
            for etapa in ('conexao', 'consulta', 'paginacao'):
                with self.subTest(path=path, etapa=etapa):
                    self.cassandra.side_effect = RuntimeError('detalhe privado') if etapa == 'conexao' else None
                    self.session.execute.side_effect = RuntimeError('detalhe privado') if etapa == 'consulta' else None
                    self.session.execute.return_value = paginas() if etapa == 'paginacao' else []
                    response = self.client.get('/api/historico/' + path)
                    self.assertEqual(response.status_code, 503)
                    self.assertIn('histórico indisponível', response.json()['detail'])
                    self.assertNotIn('detalhe privado', response.text)
