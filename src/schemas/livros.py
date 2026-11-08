from pydantic import BaseModel, Field, field_validator


class LivroCriar(BaseModel):
    titulo: str = Field(min_length=1, max_length=250)
    autores: list[str] = Field(min_length=1, max_length=30)
    generos: list[str] = Field(min_length=1, max_length=30)
    isbn: str | None = Field(default=None, max_length=30)
    ano: int | None = Field(default=None, ge=1, le=2100)
    quantidade: int = Field(default=1, ge=0, le=100000)

    @field_validator('titulo', mode='before')
    @classmethod
    def limpar_titulo(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('autores', 'generos')
    @classmethod
    def limpar_lista(cls, value):
        value = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not value or any(len(item) > 120 for item in value):
            raise ValueError('informe ao menos um valor de até 120 caracteres')
        return value


class EstoqueAtualizar(BaseModel):
    quantidade: int = Field(ge=0, le=100000)
