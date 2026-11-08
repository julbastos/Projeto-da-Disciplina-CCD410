from pydantic import BaseModel, Field


class EmprestimoCriar(BaseModel):
    usuario_id: int = Field(gt=0)
    livro_id: str


class EmprestimoAtualizar(BaseModel):
    devolvido: bool
