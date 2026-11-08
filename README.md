# biblioteca plural

trabalho de persistência poliglota com uma api fastapi e uma interface de gestão da biblioteca.

- postgres: usuários, estoque e registro transacional dos empréstimos.
- mongodb: livros com listas de autores e gêneros.
- cassandra: histórico por usuário e por livro, com duas tabelas orientadas às consultas.

## executar

use python 3.14 e o ambiente existente, ou instale as dependências com `pip install -r requirements.txt`.

1. preencha o `.env` conforme `.env.example`.
2. coloque o arquivo de conexão segura baixado no astra no caminho de `ASTRA_BUNDLE_PATH`. o token sozinho não substitui esse arquivo. o keyspace de `ASTRA_KEYSPACE` precisa existir no astra.
3. execute `python cloud/setup_cloud.py` para preparar os três bancos sem apagar dados existentes.
4. execute `python -m uvicorn app:app --app-dir src --reload`.
5. abra `http://localhost:8000`. a documentação interativa fica em `/docs`.

com uv, use `uv sync` e prefixe os comandos python com `uv run`.

para aplicar somente as migrações relacionais: `PYTHONPATH=src alembic upgrade head`. não é necessário executar o setup e o alembic juntos; ambos preparam o mesmo esquema relacional de forma aditiva.

## interface

cadastre leitores e livros, ajuste a quantidade disponível, registre empréstimos e devoluções. a busca do acervo considera título, autor e gênero. a tela de bancos verifica as conexões e permite consultar diretamente as projeções do cassandra usando o id do leitor ou do livro.

as listas exibem até 200 livros e operações. o id do livro aparece também na resposta da api; o id do leitor aparece na tabela de leitores.

## consistência entre os bancos

a retirada de um exemplar e a criação do empréstimo são feitas na mesma transação do postgres. a devolução só é aceita uma vez e repõe o exemplar na mesma transação. os ids dos empréstimos são timeuuid, compatíveis com o esquema existente do cassandra.

como não existe uma transação única entre postgres e cassandra, o postgres mantém uma fila durável com o campo `sincronizado`. cada operação tenta atualizar as duas projeções no cassandra. se falhar, o empréstimo continua registrado e fica pendente. o botão de sincronização repete até 100 registros por chamada; repetir a operação não duplica o histórico, pois usa a mesma chave. um lock no postgres serializa projeções e devoluções para evitar sobrescrever o estado devolvido com uma cópia antiga.

livros são inseridos no mongodb antes do estoque; se o postgres falhar, a api tenta remover o documento recém-criado. uma interrupção abrupta entre bancos ainda pode exigir reconciliação manual. não há transação distribuída.

## testes

instale o cliente de testes com `pip install -r requirements-dev.txt` e execute:

`PYTHONPATH=src python -m unittest discover -s tests -v`

os testes usam sqlite e substitutos locais para verificar as regras transacionais, validações e respostas da api sem alterar os serviços de nuvem.

esta interface é uma ferramenta acadêmica de administração, sem autenticação. execute em ambiente local ou de acesso restrito.

## referência

estrutura inspirada em [polyglot_backend](https://github.com/giovanni1351/Polyglot_BackEnd), adaptada aos modelos de biblioteca deste repositório.

## verificação nesta entrega

- sete testes automatizados passaram.
- conexões reais com postgres e mongodb confirmadas; migração aditiva e índices aplicados.
- geração offline da migração alembic, importação da aplicação e sintaxe do javascript verificadas.
- cassandra não foi validado: o arquivo de conexão segura indicado no `.env` não estava presente.
- a página respondeu com sucesso por http. a verificação visual com chromium foi tentada, mas o ambiente não possui a biblioteca de sistema `libatk-1.0.so.0`; os layouts ainda precisam de conferência visual.
