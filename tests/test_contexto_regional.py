"""Impede comparar calor em conjuntos diferentes de datas."""
from datetime import date
import unittest
from unittest.mock import patch

import pandas as pd

from contexto_regional import comparar_exposicao
from dados import grade_horaria


class TestContextoRegional(unittest.TestCase):
    def test_dia_quente_sem_medicao_na_estacao_nao_entra_na_comparacao(self):
        grade = grade_horaria(date(2024, 1, 1), date(2024, 1, 2))
        horarios = pd.DataFrame({"temperatura_c": [35.] * 24 + [20.] * 24}, index=grade)
        for campo in ["umidade_pct", "vento_ms", "radiacao_wm2", "precipitacao_mm"]:
            horarios[campo] = float("nan")
        estacao = pd.DataFrame({"temperatura_inmet_c": [float("nan")] * 24 + [21.] * 24}, index=grade)
        catalogo = pd.DataFrame([{"referencia": "a", "estacao": "Estação teste", "codigo": "A000", "distancia_km": 12}])
        with patch("contexto_regional.manifesto", return_value=()), \
             patch("contexto_regional.referencias", return_value=({"a": estacao}, catalogo, None, None)), \
             patch("contexto_regional.st.dataframe") as exibicao, \
             patch("contexto_regional.st.caption"):
            comparar_exposicao(horarios, 30)
        tabela = exibicao.call_args.args[0]
        self.assertEqual(tabela["Dias válidos em comum"].tolist(), [1, 1])
        self.assertEqual(tabela["Dias com máxima ≥ limiar (%)"].tolist(), [0, 0])
        self.assertEqual(tabela["Dias válidos na fonte"].tolist(), [2, 1])
