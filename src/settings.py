from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    POSTGRES_URL: str
    MONGO_URL: str
    ASTRA_BUNDLE_PATH: str = './secure-connect-biblioteca.zip'
    ASTRA_BUNDLE_BASE64: str = ''
    ASTRA_TOKEN: str = ''
    ASTRA_KEYSPACE: str = 'biblioteca'


SETTINGS = Settings()
