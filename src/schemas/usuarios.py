from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class UsuarioCriar(BaseModel):
    nome: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=180)
    telefone: str = Field(default='', max_length=30)
    matricula: str = Field(default='', max_length=40)

    @field_validator('nome', 'email', 'telefone', 'matricula', mode='before')
    @classmethod
    def limpar(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('email')
    @classmethod
    def validar_email(cls, value):
        if value.count('@') != 1 or '.' not in value.split('@')[1] or any(c.isspace() for c in value):
            raise ValueError('informe um email válido')
        return value.lower()


class Usuario(UsuarioCriar):
    id: int
    criado_em: datetime
