-- migração aditiva: preserva os usuários e o estoque existentes.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefone VARCHAR(30) NOT NULL DEFAULT '';
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS matricula VARCHAR(40) NOT NULL DEFAULT '';

-- coordena estoque e empréstimos em uma única transação e permite repetir a
-- projeção no cassandra quando ele estiver indisponível.
CREATE TABLE IF NOT EXISTS emprestimos (
    id UUID PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id),
    livro_id VARCHAR(64) NOT NULL REFERENCES estoque(livro_id),
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    devolvido BOOLEAN NOT NULL DEFAULT false,
    sincronizado BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS emprestimos_usuario ON emprestimos(usuario_id, criado_em DESC);
CREATE INDEX IF NOT EXISTS emprestimos_livro ON emprestimos(livro_id, criado_em DESC);
