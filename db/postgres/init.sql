-- RDB: usuários e estoque. Integridade garantida por restrições.

CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    email       VARCHAR(180) NOT NULL UNIQUE,
    criado_em   TIMESTAMP NOT NULL DEFAULT now()
);

-- livro_id referencia o _id (string) do documento no MongoDB.
CREATE TABLE IF NOT EXISTS estoque (
    livro_id    VARCHAR(64) PRIMARY KEY,
    quantidade  INT NOT NULL CHECK (quantidade >= 0)
);
