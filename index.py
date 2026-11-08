"""Entrada da Vercel para a aplicação que também roda localmente em src/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from app import app
