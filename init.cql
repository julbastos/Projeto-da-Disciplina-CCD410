-- DB2 (Cassandra): histórico de empréstimos, uma tabela por consulta.

CREATE KEYSPACE IF NOT EXISTS biblioteca
  WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3};

USE biblioteca;

-- Consulta: "quais empréstimos este usuário fez?" (mais recentes primeiro)
CREATE TABLE IF NOT EXISTS emprestimos_por_usuario (
    usuario_id      int,
    emprestimo_em   timeuuid,
    livro_id        text,
    devolvido       boolean,
    PRIMARY KEY ((usuario_id), emprestimo_em)
) WITH CLUSTERING ORDER BY (emprestimo_em DESC);

-- Consulta: "quem já pegou este livro?" (mais recentes primeiro)
CREATE TABLE IF NOT EXISTS emprestimos_por_livro (
    livro_id        text,
    emprestimo_em   timeuuid,
    usuario_id      int,
    devolvido       boolean,
    PRIMARY KEY ((livro_id), emprestimo_em)
) WITH CLUSTERING ORDER BY (emprestimo_em DESC);
