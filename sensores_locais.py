"""Leitura e processamento dos sensores físicos (dataloggers) instalados em locais próximos de Heliópolis.

Estes arquivos contêm medições a cada 10 minutos de temperatura e umidade registradas
por aparelhos físicos disponibilizados nos materiais do UNAS.
"""
from pathlib import Path
import pandas as pd
import streamlit as st

DIR_LOCAIS = Path(__file__).parent / "dados_saude" / "locaisproximos"

MAPEAMENTO_PONTOS = {
    "Cinga (COHAB / Pilões)": {
        "arquivo": "Cinga.CSV",
        "descricao": "Rua Attílio Bartalini / Rua Brasil viela Paulista",
        "regiao": "COHAB / Pilões",
    },
    "Jhorman": {
        "arquivo": "Jhorman.CSV",
        "descricao": "Rua João Lanhoso, 241",
        "regiao": "Jhorman / Heliópolis",
    },
    "Lagoa": {
        "arquivo": "Lagoa.CSV",
        "descricao": "Rua Flor do Pinhal, 12",
        "regiao": "Lagoa",
    },
    "Saraiva Lagoa 2": {
        "arquivo": "Saraiva Lagoa 2.CSV",
        "descricao": "Travessa Riga, 34",
        "regiao": "Saraiva-Lagoa",
    },
    "Yago": {
        "arquivo": "Yago.CSV",
        "descricao": "Rua Cristo Redentor, 468 - Bloco B",
        "regiao": "Yago / Heliópolis",
    },
}


@st.cache_data(show_spinner=False)
def carregar_sensor_local(nome_ponto: str) -> pd.DataFrame | None:
    """Lê e padroniza a série temporal de um sensor local."""
    info = MAPEAMENTO_PONTOS.get(nome_ponto)
    if not info:
        return None

    caminho = DIR_LOCAIS / info["arquivo"]
    if not caminho.is_file():
        return None

    try:
        df = pd.read_csv(
            caminho,
            sep=";",
            decimal=",",
            encoding="latin1",
            usecols=[1, 2, 3],
        )
        df.columns = ["data_hora", "temperatura_c", "umidade_pct"]
        df["data_hora"] = pd.to_datetime(df["data_hora"], errors="coerce")
        df["temperatura_c"] = pd.to_numeric(df["temperatura_c"], errors="coerce")
        df["umidade_pct"] = pd.to_numeric(df["umidade_pct"], errors="coerce")
        df = df.dropna(subset=["data_hora", "temperatura_c"])
        df = df.sort_values("data_hora").reset_index(drop=True)
        return df
    except Exception:
        return None


def obter_resumo_sensor(df: pd.DataFrame) -> dict:
    """Calcula estatísticas básicas da série de medição local."""
    if df is None or df.empty:
        return {}

    return {
        "inicio": df["data_hora"].min(),
        "fim": df["data_hora"].max(),
        "total_registros": len(df),
        "temp_min": df["temperatura_c"].min(),
        "temp_media": df["temperatura_c"].mean(),
        "temp_max": df["temperatura_c"].max(),
        "umidade_min": df["umidade_pct"].min(),
        "umidade_media": df["umidade_pct"].mean(),
        "umidade_max": df["umidade_pct"].max(),
    }


def agregar_diario_sensor(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega as leituras de 10 em 10 minutos em médias e máximas diárias."""
    if df is None or df.empty:
        return pd.DataFrame()

    df_copia = df.copy()
    df_copia["data"] = df_copia["data_hora"].dt.date
    agregado = df_copia.groupby("data").agg(
        temp_max=("temperatura_c", "max"),
        temp_media=("temperatura_c", "mean"),
        temp_min=("temperatura_c", "min"),
        umidade_media=("umidade_pct", "mean"),
        registros=("temperatura_c", "count"),
    ).reset_index()
    agregado["data"] = pd.to_datetime(agregado["data"])
    return agregado


@st.cache_data(show_spinner=False)
def media_todos_sensores() -> pd.DataFrame:
    """Calcula a média diária de temperatura e umidade entre todos os sensores disponíveis.

    Para cada dia em que pelo menos um sensor possui leitura, calcula a média
    das médias diárias de cada ponto (cada sensor tem peso igual, independentemente
    do número de leituras brutas que registrou naquele dia). Dias em que nenhum
    sensor possui dados são omitidos.

    Retorna um DataFrame com colunas:
        data, temp_max, temp_media, temp_min, umidade_media,
        sensores_no_dia (quantos pontos contribuíram), pontos (lista dos nomes)
    """
    series_diarias = []
    for nome_ponto, info in MAPEAMENTO_PONTOS.items():
        df = carregar_sensor_local(nome_ponto)
        if df is None or df.empty:
            continue
        diario = agregar_diario_sensor(df)
        diario = diario.rename(columns={
            "temp_max": f"temp_max_{nome_ponto}",
            "temp_media": f"temp_media_{nome_ponto}",
            "temp_min": f"temp_min_{nome_ponto}",
            "umidade_media": f"umidade_media_{nome_ponto}",
        })
        diario = diario.set_index("data")[[
            f"temp_max_{nome_ponto}",
            f"temp_media_{nome_ponto}",
            f"temp_min_{nome_ponto}",
            f"umidade_media_{nome_ponto}",
        ]]
        series_diarias.append((nome_ponto, diario))

    if not series_diarias:
        return pd.DataFrame()

    # Junta todos em uma tabela larga pelo índice de data (outer join = todos os dias)
    tabela = pd.concat([d for _, d in series_diarias], axis=1, join="outer")

    # Extrai colunas por tipo de métrica
    nomes = [n for n, _ in series_diarias]
    cols_max = [f"temp_max_{n}" for n in nomes]
    cols_media = [f"temp_media_{n}" for n in nomes]
    cols_min = [f"temp_min_{n}" for n in nomes]
    cols_umid = [f"umidade_media_{n}" for n in nomes]

    resultado = pd.DataFrame(index=tabela.index)
    resultado["temp_max"] = tabela[cols_max].mean(axis=1, skipna=True)
    resultado["temp_media"] = tabela[cols_media].mean(axis=1, skipna=True)
    resultado["temp_min"] = tabela[cols_min].mean(axis=1, skipna=True)
    resultado["umidade_media"] = tabela[cols_umid].mean(axis=1, skipna=True)

    # Conta quantos sensores contribuíram em cada dia
    resultado["sensores_no_dia"] = tabela[cols_media].notna().sum(axis=1)

    # Nomes dos pontos que cobrem cada dia
    resultado["pontos"] = tabela[cols_media].apply(
        lambda row: ", ".join(n for n, c in zip(nomes, cols_media) if pd.notna(row[c])),
        axis=1,
    )

    resultado = resultado[resultado["sensores_no_dia"] > 0].reset_index()
    resultado = resultado.rename(columns={"index": "data"})
    return resultado


@st.cache_data(show_spinner=False)
def conjunto_media_sensores() -> dict:
    """Calcula a média horária entre os 5 sensores locais e devolve um conjunto pronto para o painel.

    Cada sensor é amostrado de 10 em 10 minutos. Agrupamos por hora (média dos registros da hora)
    e depois tiramos a média entre os sensores presentes em cada hora, preservando a variação
    diurna (tarde mais quente, noite mais fresca) e a umidade real dos aparelhos.
    """
    from dados import FUSO, VARIAVEIS, limpar_horarios

    series_temp = []
    series_umid = []

    for nome_ponto in MAPEAMENTO_PONTOS:
        df = carregar_sensor_local(nome_ponto)
        if df is None or df.empty:
            continue
        df_hora = df.set_index("data_hora").resample("1h").mean()
        s_t = df_hora["temperatura_c"].rename(nome_ponto)
        s_u = df_hora["umidade_pct"].rename(nome_ponto)
        series_temp.append(s_t)
        series_umid.append(s_u)

    if not series_temp:
        raise ValueError("Nenhum dado de sensor local pôde ser carregado.")

    tabela_temp = pd.concat(series_temp, axis=1, sort=True)
    tabela_umid = pd.concat(series_umid, axis=1, sort=True)

    tabela_media = pd.DataFrame(index=tabela_temp.index)
    tabela_media["temperatura_c"] = tabela_temp.mean(axis=1, skipna=True)
    tabela_media["umidade_pct"] = tabela_umid.mean(axis=1, skipna=True)

    for var in VARIAVEIS.values():
        col = var[0]
        if col not in tabela_media.columns:
            tabela_media[col] = float("nan")

    # Garante fuso horário local e depois converte para UTC (padrão do painel)
    if tabela_media.index.tz is None:
        tabela_media.index = tabela_media.index.tz_localize(FUSO, ambiguous="NaT", nonexistent="NaT")
    tabela_media.index = tabela_media.index.tz_convert("UTC")

    inicio_dt = tabela_media.index.min().tz_convert(FUSO).date()
    fim_dt = tabela_media.index.max().tz_convert(FUSO).date()

    tabela_limpa, qualidade, duplicatas = limpar_horarios(tabela_media, inicio_dt, fim_dt)

    metadados = {
        "fonte": "Média de 5 Sensores Locais de Heliópolis (UNAS)",
        "modelo": "sensores_locais_dataloggers",
        "resolucao": "Medição física local (média horária ponderada)",
        "inicio": inicio_dt.isoformat(),
        "fim": fim_dt.isoformat(),
        "latitude_solicitada": -23.615,
        "longitude_solicitada": -46.590,
        "fuso_analise": FUSO,
        "documentacao": "Média horária de dataloggers físicos (COHAB, Pilões, Jhorman, Lagoa, Saraiva, Yago)",
    }

    resposta_simulada = {
        "hourly": {
            "time": [int(ts.timestamp()) for ts in tabela_limpa.index],
            "temperature_2m": tabela_limpa["temperatura_c"].tolist(),
            "relative_humidity_2m": tabela_limpa["umidade_pct"].tolist(),
            "wind_speed_10m": tabela_limpa["vento_ms"].tolist(),
            "shortwave_radiation": tabela_limpa["radiacao_wm2"].tolist(),
            "precipitation": tabela_limpa["precipitacao_mm"].tolist(),
        },
        "hourly_units": {
            "time": "unixtime",
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "wind_speed_10m": "m/s",
            "shortwave_radiation": "W/m²",
            "precipitation": "mm",
        },
    }

    return {
        "horarios": tabela_limpa,
        "qualidade": qualidade,
        "duplicatas": duplicatas,
        "metadados": metadados,
        "resposta_api": resposta_simulada,
    }


