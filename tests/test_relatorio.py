"""Testes de casos que podem alterar a interpretação científica do relatório.

Os valores artificiais deste arquivo existem SOMENTE para testar os cálculos.
Eles nunca são carregados automaticamente pelo aplicativo.
"""

from datetime import date
from io import BytesIO
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

import pandas as pd

from analise import (episodios_quentes, gerar_relatorio,
                     indicadores_diarios, indicadores_noturnos, resumo_anual)
from dados import (ErroDados, VARIAVEIS, buscar_open_meteo, carregar_json,
                   exportar_json, grade_horaria, interpretar_api,
                   limpar_horarios, montar_conjunto)


def exemplo(inicio=date(2024, 1, 1), fim=date(2024, 1, 5)):
    """Cinco dias conhecidos permitem conferir resultados esperados à mão."""
    indice = grade_horaria(inicio, fim)
    horarios = pd.DataFrame({"temperatura_c": 32.0, "umidade_pct": 65.0,
                            "vento_ms": 2.0, "radiacao_wm2": 100.0,
                            "precipitacao_mm": 0.0}, index=indice)
    return horarios


def conjunto_exemplo(inicio=date(2024, 1, 1), fim=date(2024, 1, 5)):
    horarios = exemplo(inicio, fim)
    resposta = {"latitude": -23.5, "longitude": -46.5,
                "hourly_units": {"time": "unixtime"}, "hourly": {
                    "time": [int(t.timestamp()) for t in horarios.index]}}
    for campo, (coluna, unidade, _) in VARIAVEIS.items():
        resposta["hourly"][campo] = horarios[coluna].tolist()
        resposta["hourly_units"][campo] = unidade
    meta = {"inicio": inicio.isoformat(), "fim": fim.isoformat(), "modelo": "era5",
            "latitude_solicitada": -23.615, "longitude_solicitada": -46.590,
            "latitude_retornada": -23.5, "longitude_retornada": -46.5,
            "coletado_em_utc": "2024-02-01T00:00:00+00:00"}
    return montar_conjunto(resposta, meta)


class TestAnalise(unittest.TestCase):
    def test_dia_sem_dados_nao_vira_dia_frio(self):
        horarios = exemplo()
        horarios.iloc[24:48, horarios.columns.get_loc("temperatura_c")] = float("nan")
        diario = indicadores_diarios(horarios)
        self.assertTrue(pd.isna(diario.iloc[1].dia_quente))
        self.assertTrue(pd.isna(diario.iloc[1].temp_max_c))
        self.assertEqual(int(diario.dia_valido.sum()), 4)
        self.assertEqual(resumo_anual(diario).iloc[0].dias_quentes_pct, 100.0)

    def test_cobertura_separada_por_variavel_e_chuva_completa(self):
        horarios = exemplo()
        horarios.iloc[:8, horarios.columns.get_loc("umidade_pct")] = float("nan")
        horarios.iloc[0, horarios.columns.get_loc("precipitacao_mm")] = float("nan")
        diario = indicadores_diarios(horarios)
        self.assertTrue(diario.iloc[0].dia_valido)
        self.assertTrue(pd.isna(diario.iloc[0].umidade_pct))
        self.assertTrue(pd.isna(diario.iloc[0].precipitacao_mm))

    def test_lacuna_interrompe_episodio(self):
        horarios = exemplo(fim=date(2024, 1, 7))
        horarios.iloc[72:96, horarios.columns.get_loc("temperatura_c")] = float("nan")
        episodios = episodios_quentes(indicadores_diarios(horarios), 3)
        self.assertEqual(episodios.duracao_dias.tolist(), [3, 3])
        self.assertTrue(episodios.toca_borda_da_consulta.all())

    def test_dia_ausente_no_indice_tambem_interrompe(self):
        diario = indicadores_diarios(exemplo())
        diario = diario.drop(pd.Timestamp("2024-01-03"))
        self.assertTrue(episodios_quentes(diario, 3).empty)

    def test_limite_inclusivo_e_episodio_no_ultimo_dia(self):
        diario = indicadores_diarios(exemplo(), limiar=32)
        self.assertEqual(episodios_quentes(diario).iloc[0].duracao_dias, 5)
        self.assertTrue(episodios_quentes(indicadores_diarios(exemplo(), limiar=33)).empty)

    def test_noites_nao_misturam_madrugadas_e_excluem_bordas(self):
        horarios = exemplo()
        # A noite de 01/01 inclui a madrugada de 02/01 (UTC 03h a 08h).
        horarios.loc["2024-01-02T03:00:00Z":"2024-01-02T08:00:00Z", "temperatura_c"] = 20.0
        noites = indicadores_noturnos(horarios)
        self.assertEqual(noites.loc["2024-01-01", "temp_noturna_media_c"], 23.0)
        self.assertFalse(noites.iloc[0].noite_valida)
        self.assertFalse(noites.iloc[-1].noite_valida)
        self.assertEqual(int(noites.noite_valida.sum()), 4)

    def test_horario_verao_tem_dias_de_23_e_25_horas(self):
        self.assertEqual(len(grade_horaria(date(2018, 11, 4), date(2018, 11, 4))), 23)
        self.assertEqual(len(grade_horaria(date(2019, 2, 16), date(2019, 2, 16))), 25)
        diario = indicadores_diarios(exemplo(date(2018, 11, 3), date(2018, 11, 5)))
        self.assertEqual(diario.loc["2018-11-04", "cobertura_pct"], 100)
        noites = indicadores_noturnos(exemplo(date(2018, 11, 3), date(2018, 11, 5)))
        self.assertEqual(noites.loc["2018-11-03", "horas_esperadas"], 7)
        self.assertTrue(noites.loc["2018-11-03", "noite_valida"])

    def test_sem_dias_validos_nao_produz_percentual_zero(self):
        horarios = exemplo()
        horarios["temperatura_c"] = float("nan")
        anual = resumo_anual(indicadores_diarios(horarios))
        self.assertTrue(pd.isna(anual.iloc[0].dias_quentes_pct))
        self.assertTrue(pd.isna(anual.iloc[0].dias_quentes))

    def test_relatorio_guarda_criterios_e_limitacoes(self):
        conjunto = conjunto_exemplo()
        diario = indicadores_diarios(conjunto["horarios"])
        texto = gerar_relatorio(conjunto, diario, indicadores_noturnos(conjunto["horarios"]),
                                 episodios_quentes(diario), 30, 3, 0.9)
        self.assertIn("Dias acima do limiar: 5", texto)
        self.assertIn("90%", texto)
        self.assertIn("relações causais", texto)


class TestDados(unittest.TestCase):
    def test_limpeza_mantem_lacunas_e_remove_sentinelas(self):
        horarios = exemplo()
        horarios.iloc[0, 0] = -9999
        horarios.iloc[1, 1] = 140
        horarios = pd.concat([horarios.drop(horarios.index[2]), horarios.iloc[[3]]])
        limpa, qualidade, duplicatas = limpar_horarios(horarios, date(2024, 1, 1), date(2024, 1, 5))
        self.assertEqual(len(limpa), 120)
        self.assertEqual(duplicatas, 1)
        self.assertEqual(int(limpa.temperatura_c.isna().sum()), 2)
        self.assertEqual(int(qualidade.valores_fora_dos_limites.sum()), 2)

    def test_json_preserva_dados_e_proveniencia(self):
        original = conjunto_exemplo()
        reaberto = carregar_json(exportar_json(original))
        pd.testing.assert_frame_equal(original["horarios"], reaberto["horarios"])
        self.assertEqual(original["metadados"], reaberto["metadados"])

    def test_rejeita_unidade_incorreta(self):
        resposta = conjunto_exemplo()["resposta_api"]
        resposta["hourly_units"]["wind_speed_10m"] = "km/h"
        with self.assertRaises(ErroDados):
            interpretar_api(resposta, date(2024, 1, 1), date(2024, 1, 5))

    def test_json_invalido_gera_mensagem_compreensivel(self):
        for conteudo in [b"{}", b"[]", b"nao e json", b'{"versao":1,"metadados":null}']:
            with self.subTest(conteudo=conteudo), self.assertRaises(ErroDados):
                carregar_json(conteudo)

    def test_api_consulta_um_modelo_unidades_e_horas_utc(self):
        resposta = conjunto_exemplo()["resposta_api"]
        with patch("dados.urlopen", return_value=BytesIO(json.dumps(resposta).encode())) as conexao:
            conjunto = buscar_open_meteo(date(2024, 1, 1), date(2024, 1, 5))
        url = conexao.call_args.args[0].full_url
        self.assertIn("models=era5", url)
        self.assertIn("timeformat=unixtime", url)
        self.assertIn("wind_speed_unit=ms", url)
        self.assertIn("end_date=2024-01-06", url)
        self.assertEqual(len(conjunto["horarios"]), 120)

    def test_falha_rede_nao_produz_dados_ficticios(self):
        with patch("dados.urlopen", side_effect=URLError("offline")), self.assertRaises(ErroDados):
            buscar_open_meteo(date(2024, 1, 1), date(2024, 1, 5))

    def test_periodo_invertido_nao_dispara_consulta(self):
        with patch("dados.urlopen") as conexao, self.assertRaises(ErroDados):
            buscar_open_meteo(date(2024, 2, 1), date(2024, 1, 1))
        conexao.assert_not_called()



if __name__ == "__main__":
    unittest.main()
