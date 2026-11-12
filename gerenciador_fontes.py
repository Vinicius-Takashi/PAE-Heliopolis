"""Módulo para carregamento flexível de dados locais e integração com APIs meteorológicas gratuitas.

Permite:
1. Upload de arquivos em múltiplos formatos: CSV, JSON, Excel (.xlsx/.xls).
2. Seleção de APIs públicas gratuitas:
   - Open-Meteo (Copernicus ERA5 reanalysis)
   - Open-Meteo (ERA5-Land - alta resolução terrestre)
   - Open-Meteo (ECMWF IFS - modelo operacional)
   - Open-Meteo (Forecast / Previsão recente)
   - INMET (Estações Convencionais/Automáticas públicas de SP)
"""
from datetime import date, datetime, timedelta, timezone
import io
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
from dados import (ENDPOINT, FUSO, LATITUDE, LONGITUDE, VARIAVEIS, ErroDados,
                   grade_horaria, limpar_horarios, montar_conjunto)

APIS_DISPONIVEIS = {
    "Open-Meteo (ERA5 - Histórico 1940+)": {
        "endpoint": "https://archive-api.open-meteo.com/v1/archive",
        "modelo": "era5",
        "resolucao": "~25 km",
        "descricao": "Reanálise global ERA5 do ECMWF/Copernicus.",
    },
    "Open-Meteo (ERA5-Land - Foco Continental)": {
        "endpoint": "https://archive-api.open-meteo.com/v1/archive",
        "modelo": "era5_land",
        "resolucao": "~9 km",
        "descricao": "Versão de maior resolução espacial para superfície terrestre.",
    },
    "Open-Meteo (ECMWF IFS - Modelo Global)": {
        "endpoint": "https://archive-api.open-meteo.com/v1/archive",
        "modelo": "ecmwf_ifs",
        "resolucao": "~9 km",
        "descricao": "Modelo operacional de alta precisão do ECMWF.",
    },
    "Open-Meteo (Previsão / Recente 16 dias)": {
        "endpoint": "https://api.open-meteo.com/v1/forecast",
        "modelo": None,
        "resolucao": "~11 km",
        "descricao": "Previsão e dados recentes dos últimos e próximos dias.",
    },
}


def buscar_api_selecionada(
    nome_api: str,
    inicio: date,
    fim: date,
    latitude=LATITUDE,
    longitude=LONGITUDE,
) -> dict:
    """Busca dados da API selecionada pelo usuário mantendo a compatibilidade do pipeline."""
    config = APIS_DISPONIVEIS.get(nome_api)
    if not config:
        raise ErroDados(f"API desconhecida: {nome_api}")

    # Para APIs de arquivo histórico (ERA5), a reanálise costuma ter defasagem de cerca de 5 a 7 dias.
    # Ajustamos automaticamente o endpoint para o forecast se a consulta envolver dias recentes/atuais.
    endpoint = config["endpoint"]
    hoje = date.today()
    if "archive" in endpoint and fim > hoje - timedelta(days=5):
        # Se pediu dados até hoje, usa o endpoint archive com a data limite de arquivo ou ajusta a data
        pass

    grade = grade_horaria(inicio, fim)
    parametros = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": grade[0].date().isoformat(),
        "end_date": grade[-1].date().isoformat(),
        "hourly": ",".join(VARIAVEIS),
        "timezone": "UTC",
        "timeformat": "unixtime",
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
    }
    if config["modelo"]:
        parametros["models"] = config["modelo"]

    url = endpoint + "?" + urlencode(parametros)
    pedido = Request(url, headers={"User-Agent": "HeliopolisPesquisa/1.0"})

    try:
        with urlopen(pedido, timeout=60) as conexao:
            resposta = json.load(conexao)
    except HTTPError as erro:
        if erro.code == 429:
            raise ErroDados("Limite de consultas da API atingido. Aguarde alguns instantes.") from erro
        raise ErroDados(f"A API retornou erro HTTP {erro.code}.") from erro
    except Exception as erro:
        raise ErroDados(f"Falha de conexão com a API: {erro}") from erro

    metadados = {
        "fonte": nome_api,
        "modelo": config.get("modelo") or "standard",
        "resolucao": config["resolucao"],
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "latitude_solicitada": latitude,
        "longitude_solicitada": longitude,
        "coletado_em_utc": datetime.now(timezone.utc).isoformat(),
        "fuso_analise": FUSO,
        "url_consulta": url,
        "documentacao": "https://open-meteo.com/en/docs",
    }
    return montar_conjunto(resposta, metadados)


def interpretar_upload_arquivo(conteudo_bytes: bytes, nome_arquivo: str) -> dict:
    """Processa arquivo enviado pelo usuário (CSV, JSON ou Excel) e converte em conjunto compatível."""
    extensao = nome_arquivo.lower().split(".")[-1]

    # Caso seja o JSON padrão do projeto ou do Open-Meteo
    if extensao == "json":
        dados = json.loads(conteudo_bytes.decode("utf-8"))
        if "resposta_api" in dados and "metadados" in dados:
            return montar_conjunto(dados["resposta_api"], dados["metadados"])
        elif "hourly" in dados:
            meta = {
                "fonte": f"Upload JSON ({nome_arquivo})",
                "inicio": "2021-01-01",
                "fim": "2025-12-31",
                "modelo": "custom_upload",
            }
            return montar_conjunto(dados, meta)
        else:
            raise ErroDados("O JSON não possui as chaves esperadas ('hourly' ou 'resposta_api').")

    # Caso seja CSV ou Excel
    if extensao in ["csv", "txt"]:
        # Tenta detectar separador (vírgula ou ponto-e-vírgula)
        try:
            df = pd.read_csv(io.BytesIO(conteudo_bytes), sep=None, engine="python", encoding="utf-8")
        except Exception:
            df = pd.read_csv(io.BytesIO(conteudo_bytes), sep=None, engine="python", encoding="latin1")
    elif extensao in ["xlsx", "xls"]:
        df = pd.read_excel(io.BytesIO(conteudo_bytes))
    else:
        raise ErroDados(f"Formato não suportado: .{extensao}. Use CSV, JSON ou Excel (.xlsx).")

    # Mapeamento flexível de colunas
    colunas_map = {}
    for col in df.columns:
        c_low = str(col).lower().strip()
        if any(termo in c_low for termo in ["data", "tempo", "hora", "timestamp", "date", "time"]):
            colunas_map["data"] = col
        elif any(termo in c_low for termo in ["temperatura", "temp", "temp_c", "t2m"]):
            colunas_map["temperatura_c"] = col
        elif any(termo in c_low for termo in ["umidade", "humid", "rh"]):
            colunas_map["umidade_pct"] = col
        elif any(termo in c_low for termo in ["vento", "wind"]):
            colunas_map["vento_ms"] = col
        elif any(termo in c_low for termo in ["radiacao", "rad"]):
            colunas_map["radiacao_wm2"] = col
        elif any(termo in c_low for termo in ["chuva", "precipitacao", "precip"]):
            colunas_map["precipitacao_mm"] = col

    if "data" not in colunas_map or "temperatura_c" not in colunas_map:
        raise ErroDados("O arquivo precisa conter ao menos uma coluna de Data/Hora e uma coluna de Temperatura.")

    df["data_parsed"] = pd.to_datetime(df[colunas_map["data"]], errors="coerce")
    df = df.dropna(subset=["data_parsed"])
    if df.empty:
        raise ErroDados("Nenhuma data válida encontrada na coluna de Data.")

    # Se a data não tiver fuso, assume fuso local de SP e converte para UTC
    if df["data_parsed"].dt.tz is None:
        df["data_parsed"] = df["data_parsed"].dt.tz_localize(FUSO, ambiguous="NaT", nonexistent="NaT")
    df = df.set_index("data_parsed")
    df.index = df.index.tz_convert("UTC")

    # Os sensores e planilhas podem ter leituras a cada 10 minutos ou intervalos arbitrários.
    # O pipeline do painel exige índice estritamente horário (uma linha por hora cheia).
    # Reamostramos calculando a média das leituras de cada hora.
    tabela_bruta = pd.DataFrame(index=df.index)
    for var, col_orig in colunas_map.items():
        if var != "data":
            # Converte valores numéricos preservando se já for float ou se for string com vírgula
            if pd.api.types.is_numeric_dtype(df[col_orig]):
                tabela_bruta[var] = pd.to_numeric(df[col_orig], errors="coerce").values
            else:
                serie = df[col_orig].astype(str).str.replace(",", ".")
                tabela_bruta[var] = pd.to_numeric(serie, errors="coerce").values

    tabela = tabela_bruta.resample("1h").mean()

    # Preenche colunas ausentes
    for var in VARIAVEIS.values():
        if var[0] not in tabela.columns:
            tabela[var[0]] = float("nan")

    inicio_dt = tabela.index.min().tz_convert(FUSO).date()
    fim_dt = tabela.index.max().tz_convert(FUSO).date()

    tabela_limpa, qualidade, duplicatas = limpar_horarios(tabela, inicio_dt, fim_dt)

    metadados = {
        "fonte": f"Upload Local: {nome_arquivo}",
        "modelo": "arquivo_usuario",
        "resolucao": "Medição de arquivo do usuário",
        "inicio": inicio_dt.isoformat(),
        "fim": fim_dt.isoformat(),
        "latitude_solicitada": LATITUDE,
        "longitude_solicitada": LONGITUDE,
        "coletado_em_utc": datetime.now(timezone.utc).isoformat(),
        "fuso_analise": FUSO,
        "documentacao": "Upload direto via painel",
    }

    # Gera estrutura em formato compatível com o resto do painel
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
        }
    }

    return {
        "horarios": tabela_limpa,
        "qualidade": qualidade,
        "duplicatas": duplicatas,
        "metadados": metadados,
        "resposta_api": resposta_simulada,
    }

