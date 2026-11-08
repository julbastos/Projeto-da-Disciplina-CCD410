-- fila de exclusões pendentes no cassandra, sem dependência dos cadastros.
CREATE TABLE IF NOT EXISTS emprestimos_excluidos (
    id UUID PRIMARY KEY,
    usuario_id INT NOT NULL,
    livro_id VARCHAR(64) NOT NULL
);
