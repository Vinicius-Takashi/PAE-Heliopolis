"""Confere os fluxos da interface sem depender da rede ou de um navegador."""

from pathlib import Path
from contextlib import contextmanager
from datetime import date
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from dados import ErroDados, exportar_json
from test_relatorio import conjunto_exemplo


APP = str(Path(__file__).resolve().parents[1] / "app.py")


@contextmanager
def base_local_de_teste(conjunto):
    """Simula só a base do projeto: não requer internet nem dados_locais no disco."""
    existe_original = Path.is_file
    leitura_original = Path.read_bytes
    conteudo = exportar_json(conjunto)

    def existe(caminho):
        return True if caminho.name == "heliopolis_open_meteo.json" else existe_original(caminho)

    def ler(caminho):
        return conteudo if caminho.name == "heliopolis_open_meteo.json" else leitura_original(caminho)

    with patch.object(Path, "is_file", existe), patch.object(Path, "read_bytes", ler):
        yield


class TestInterface(unittest.TestCase):
    def test_base_local_abre_diretamente_sem_rede_ou_abas(self):
        # Uma base antiga deve ser cortada antes de alimentar cartões e filtros.
        conjunto = conjunto_exemplo(date(2020, 12, 29), date(2021, 1, 5))
        with base_local_de_teste(conjunto), patch("dados.urlopen") as rede:
            painel = AppTest.from_file(APP, default_timeout=30).run()
        self.assertFalse(painel.exception)
        rede.assert_not_called()
        self.assertEqual(len(painel.title), 1)
        self.assertEqual(len(painel.tabs), 0)
        self.assertEqual(len(painel.metric), 4)
        self.assertEqual(len(painel.sidebar), 0)
        self.assertEqual(painel.metric[1].value, "5")
        self.assertEqual(painel.selectbox(key="periodo").options, ["Todo o período", "2021"])

    def test_carga_e_filtro_recalculam_os_indicadores(self):
        painel = AppTest.from_file(APP, default_timeout=30)
        painel.session_state["conjunto"] = conjunto_exemplo()
        painel.session_state["origem_carregada"] = "Fixture exclusiva de teste"
        painel.run()
        self.assertFalse(painel.exception)
        self.assertEqual(painel.metric[1].value, "5")
        self.assertEqual(painel.metric[2].value, "1")
        painel.slider(key="limiar").set_value(33.0).run()
        self.assertFalse(painel.exception)
        self.assertEqual(painel.metric[1].value, "0")
        self.assertEqual(painel.metric[2].value, "0")

    def test_filtro_de_ano_restringe_periodo_e_indicadores(self):
        conjunto = conjunto_exemplo(date(2023, 12, 29), date(2024, 1, 5))
        with base_local_de_teste(conjunto), patch("dados.urlopen") as rede:
            painel = AppTest.from_file(APP, default_timeout=30).run()
            self.assertEqual(painel.metric[1].value, "8")
            painel.selectbox(key="periodo").select("2024").run()
        self.assertFalse(painel.exception)
        rede.assert_not_called()
        self.assertEqual(painel.metric[1].value, "5")
        self.assertTrue(any("01/01/2024 a 05/01/2024" in texto.value for texto in painel.caption))

    def test_painel_apenas_exploratorio_e_limites_explicitos(self):
        painel = AppTest.from_file(APP, default_timeout=30)
        painel.session_state["conjunto"] = conjunto_exemplo()
        painel.run()
        self.assertFalse(painel.exception)
        self.assertEqual(len(painel.button), 0)
        self.assertEqual(len(painel.get("file_uploader")), 0)
        self.assertEqual(len(painel.get("download_button")), 0)
        self.assertEqual(len(painel.date_input), 0)
        self.assertTrue(any("Observatório De Olho na Quebrada" in aviso.value for aviso in painel.info))
        self.assertTrue(any("não medem impactos" in aviso.value for aviso in painel.info))
        self.assertEqual(painel.metric[1].value, "5")


if __name__ == "__main__":
    unittest.main()
