"""Verifica fronteiras de data, lacunas e preservação das estações."""
import unittest
from unittest.mock import patch

import pandas as pd

from inmet_local import tratar, distancia_km


class TestInmetLocal(unittest.TestCase):
    def test_distancia(self):
        self.assertAlmostEqual(distancia_km(-23.615, -46.590), 0)
        self.assertTrue(13 < distancia_km(-23.496294, -46.620088) < 14)

    def test_fronteira_conflito_e_coordenadas(self):
        meta = {"LATITUDE": "-23.496294", "LONGITUDE": "-46.620088",
                "CODIGO (WMO)": "A701", "ESTACAO": "Mirante"}
        indice = pd.to_datetime(["2021-01-01 02:00Z", "2021-01-01 03:00Z",
                                "2026-01-01 02:00Z", "2026-01-01 03:00Z"])
        a = pd.DataFrame({"temperatura_inmet_c": [20, 25, 30, 35]}, index=indice)
        b = a.copy()
        b.iloc[1, 0] = 26
        with patch("inmet_local.cabecalho", side_effect=[meta, {**meta, "LATITUDE": "-23.496389"}]), \
             patch("inmet_local.Path.read_bytes", return_value=b""), \
             patch("inmet_local.ler_inmet", side_effect=[(a, {}), (b, {})]):
            series, catalogo, anual, auditoria = tratar((("a", 0, 0), ("b", 0, 0)))
        self.assertEqual(len(series), 1)
        tabela = next(iter(series.values()))
        self.assertEqual(len(tabela), 43824)
        self.assertTrue(pd.isna(tabela.iloc[0, 0]))
        self.assertEqual(tabela.iloc[-1, 0], 30)
        self.assertEqual(catalogo.iloc[0].conflitos_entre_arquivos, 1)
        self.assertEqual(catalogo.iloc[0].horas_validas, 1)
        self.assertEqual(len(anual), 5)


if __name__ == "__main__":
    unittest.main()
