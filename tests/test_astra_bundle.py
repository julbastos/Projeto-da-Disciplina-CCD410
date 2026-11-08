import base64
import binascii
from pathlib import Path
import unittest
from unittest.mock import patch

from database import astra_bundle
from settings import ROOT, SETTINGS


class AstraBundleTest(unittest.TestCase):
    def test_configuracao_local_preserva_caminho(self):
        with patch.object(SETTINGS, 'ASTRA_BUNDLE_BASE64', ''):
            with astra_bundle() as path:
                self.assertEqual(path, str(ROOT / SETTINGS.ASTRA_BUNDLE_PATH))

    def test_base64_tem_prioridade_e_arquivo_temporario_e_removido(self):
        data = b'conteudo do bundle'
        with patch.object(SETTINGS, 'ASTRA_BUNDLE_BASE64', base64.b64encode(data).decode()):
            with astra_bundle() as path:
                temp = Path(path)
                self.assertEqual(temp.parent, Path('/tmp'))
                self.assertEqual(temp.read_bytes(), data)
                self.assertEqual(temp.stat().st_mode & 0o777, 0o600)
            self.assertFalse(temp.exists())

    def test_base64_invalido_falha(self):
        with patch.object(SETTINGS, 'ASTRA_BUNDLE_BASE64', 'invalido!'):
            with self.assertRaises(binascii.Error):
                with astra_bundle():
                    self.fail('base64 inválido foi aceito')
