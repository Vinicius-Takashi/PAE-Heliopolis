"""Coleta e leitura dos dados. Dependências externas: somente Pandas.

A conexão HTTP usa urllib, que já vem com o Python. Nenhum dado fictício é
inserido se a API falhar: o erro é apresentado para quem estiver usando o painel.
"""

from datetime import date, datetime, timedelta, timezone
from io import StringIO
import json
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


FUSO = "America/Sao_Paulo"
# Últimos cinco anos completos na definição deste estudo (outubro de 2026).
# Fixamos o intervalo para que o relatório continue reproduzível no futuro.
INICIO_ESTUDO = date(2021, 1, 1)
FIM_ESTUDO = date(2025, 12, 31)
ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"
# Ponto aproximado de consulta, e não centroide oficial nem estação instalada.
LATITUDE = -23.615
LONGITUDE = -46.590
VARIAVEIS = {
    "temperature_2m": ("temperatura_c", "°C", "Temperatura do ar a 2 m"),
    "relative_humidity_2m": ("umidade_pct", "%", "Umidade relativa a 2 m"),
    "wind_speed_10m": ("vento_ms", "m/s", "Vento a 10 m"),
    "shortwave_radiation": ("radiacao_wm2", "W/m²", "Radiação solar: média da hora anterior"),
    "precipitation": ("precipitacao_mm", "mm", "Precipitação: acumulado da hora anterior"),
}


class ErroDados(ValueError):
    """Mensagem de erro que pode ser mostrada diretamente no dashboard."""


def validar_periodo(inicio: date, fim: date) -> None:
    """Impede períodos invertidos ou grandes demais para o relatório inicial."""
    if inicio > fim:
        raise ErroDados("A data inicial deve ser anterior ou igual à data final.")
    if inicio < date(1940, 1, 1) or (fim - inicio).days > 366 * 15:
        raise ErroDados("Escolha até 15 anos de dados, a partir de 1940.")


def grade_horaria(inicio: date, fim: date) -> pd.DatetimeIndex:
    """Cria todas as horas esperadas, respeitando o antigo horário de verão.

    Guardamos os instantes em UTC para distinguir horas locais repetidas. Só
    convertemos para São Paulo ao agrupar os dias ou apresentar os resultados.
    """
    validar_periodo(inicio, fim)
    primeiro = pd.Timestamp(inicio).tz_localize(FUSO, nonexistent="shift_forward")
    limite = pd.Timestamp(fim + timedelta(days=1)).tz_localize(
        FUSO, nonexistent="shift_forward"
    )
    return pd.date_range(primeiro.tz_convert("UTC"), limite.tz_convert("UTC"),
                         freq="h", inclusive="left", name="data_hora_utc")


def limpar_horarios(tabela: pd.DataFrame, inicio: date, fim: date):
    """Sinaliza valores inválidos e preserva lacunas, sem interpolar extremos."""
    tabela = tabela.copy()
    duplicatas = int(tabela.index.duplicated().sum())
    tabela = tabela.loc[~tabela.index.duplicated(keep="first")].sort_index()
    tabela = tabela.reindex(grade_horaria(inicio, fim))
    # São limites amplos de consistência, não limites de risco à saúde.
    limites = {
        "temperatura_c": (-90, 65), "umidade_pct": (0, 100),
        "vento_ms": (0, 150), "radiacao_wm2": (0, 1600),
        "precipitacao_mm": (0, 1000),
    }
    qualidade = []
    for coluna, (minimo, maximo) in limites.items():
        if coluna not in tabela:
            tabela[coluna] = float("nan")
        valores = pd.to_numeric(tabela[coluna], errors="coerce")
        invalidos = valores.notna() & ~valores.between(minimo, maximo)
        tabela[coluna] = valores.mask(invalidos)
        qualidade.append({
            "variavel": coluna, "horas_esperadas": len(tabela),
            "horas_validas": int(tabela[coluna].notna().sum()),
            "horas_ausentes_ou_invalidas": int(tabela[coluna].isna().sum()),
            "valores_fora_dos_limites": int(invalidos.sum()),
            "cobertura_pct": round(tabela[coluna].notna().mean() * 100, 2),
        })
    return tabela, pd.DataFrame(qualidade), duplicatas


def interpretar_api(resposta: dict, inicio: date, fim: date):
    """Valida o contrato da API antes de transformar o JSON em uma tabela."""
    if not isinstance(resposta, dict) or resposta.get("error"):
        raise ErroDados("A resposta não contém uma série válida do Open-Meteo.")
    horas = resposta.get("hourly", {})
    unidades = resposta.get("hourly_units", {})
    if not isinstance(horas, dict) or not isinstance(horas.get("time"), list) or not horas["time"]:
        raise ErroDados("A resposta não contém observações horárias.")
    try:
        # O pedido usa unixtime para evitar offsets fixos durante o horário de verão.
        if unidades.get("time") != "unixtime":
            raise ErroDados("O arquivo deve usar timestamps Unix, como a exportação deste painel.")
        indice = pd.to_datetime(horas["time"], unit="s", utc=True, errors="raise")
        tabela = pd.DataFrame(index=indice)
        for campo, (coluna, unidade, _) in VARIAVEIS.items():
            if campo not in horas or unidades.get(campo) != unidade:
                raise ErroDados(f"Campo ausente ou unidade inesperada: {campo} ({unidade}).")
            tabela[coluna] = horas[campo]
    except (ValueError, TypeError, OverflowError) as erro:
        raise ErroDados(f"Não foi possível interpretar a série: {erro}") from erro
    tabela, qualidade, duplicatas = limpar_horarios(tabela, inicio, fim)
    if not tabela.temperatura_c.notna().any():
        raise ErroDados("Não há temperaturas válidas no período escolhido.")
    return tabela, qualidade, duplicatas


def montar_conjunto(resposta: dict, metadados: dict):
    """Reúne dados, auditoria e origem em um único objeto para a interface."""
    try:
        inicio = date.fromisoformat(metadados["inicio"])
        fim = date.fromisoformat(metadados["fim"])
    except (KeyError, TypeError, ValueError) as erro:
        raise ErroDados("Metadados sem datas válidas de início e fim.") from erro
    tabela, qualidade, duplicatas = interpretar_api(resposta, inicio, fim)
    return {"horarios": tabela, "qualidade": qualidade,
            "duplicatas": duplicatas, "metadados": metadados, "resposta_api": resposta}


def recortar_periodo(conjunto, inicio=INICIO_ESTUDO, fim=FIM_ESTUDO):
    """Restringe dados e exportações ao intervalo, sem baixar novamente.

    Mantemos os valores originais e a URL da coleta. O JSON também é recortado,
    para que o download não leve anos que ficaram fora da análise. Datas UTC
    são comparadas com as fronteiras locais: a madrugada UTC de 01/01/2026
    ainda contém horas de 31/12/2025 em São Paulo.
    """
    validar_periodo(inicio, fim)
    meta = conjunto["metadados"]
    inicio = max(inicio, date.fromisoformat(meta["inicio"]))
    fim = min(fim, date.fromisoformat(meta["fim"]))
    if inicio > fim:
        raise ErroDados("A base não contém dados no período do estudo (2021–2025).")
    if inicio.isoformat() == meta["inicio"] and fim.isoformat() == meta["fim"]:
        return conjunto
    grade = grade_horaria(inicio, fim)
    resposta = conjunto["resposta_api"]
    instantes = pd.to_datetime(resposta["hourly"]["time"], unit="s", utc=True)
    dentro = (instantes >= grade[0]) & (instantes <= grade[-1])
    posicoes = [i for i, incluir in enumerate(dentro) if incluir]
    resposta_recortada = {**resposta, "hourly": {
        campo: [valores[i] for i in posicoes] for campo, valores in resposta["hourly"].items()
    }}
    metadados = {**meta, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
                "tratamento_temporal": "Resposta da API recortada ao período local indicado; valores preservados."}
    return montar_conjunto(resposta_recortada, metadados)


def buscar_open_meteo(inicio: date, fim: date, latitude=LATITUDE, longitude=LONGITUDE):
    """Busca dados reais de um único modelo (ERA5), sem misturar versões."""
    validar_periodo(inicio, fim)
    hoje_local = pd.Timestamp.now(tz=FUSO).date()
    if fim > hoje_local - timedelta(days=7):
        raise ErroDados("Deixe pelo menos sete dias entre o fim da consulta e hoje.")
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ErroDados("Coordenadas inválidas.")
    grade = grade_horaria(inicio, fim)
    parametros = {
        "latitude": latitude, "longitude": longitude,
        "start_date": grade[0].date().isoformat(),
        "end_date": grade[-1].date().isoformat(),
        "hourly": ",".join(VARIAVEIS), "models": "era5",
        "timezone": "UTC", "timeformat": "unixtime",
        "temperature_unit": "celsius", "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
    }
    url = ENDPOINT + "?" + urlencode(parametros)
    pedido = Request(url, headers={"User-Agent": "HeliopolisPesquisa/1.0"})
    try:
        with urlopen(pedido, timeout=60) as conexao:
            resposta = json.load(conexao)
    except HTTPError as erro:
        if erro.code == 429:
            raise ErroDados("Limite de consultas atingido. Aguarde ou carregue um JSON salvo.") from erro
        raise ErroDados(f"A API respondeu com HTTP {erro.code}. Tente novamente mais tarde.") from erro
    except (URLError, TimeoutError, OSError, ValueError) as erro:
        raise ErroDados("Não foi possível acessar a API. Verifique a conexão ou carregue um JSON salvo.") from erro
    metadados = {
        "fonte": "Open-Meteo / Copernicus ERA5", "modelo": "era5",
        "resolucao": "0,25 grau (aproximadamente 25 km)",
        "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        "latitude_solicitada": latitude, "longitude_solicitada": longitude,
        "latitude_retornada": resposta.get("latitude"),
        "longitude_retornada": resposta.get("longitude"),
        "elevacao_retornada_m": resposta.get("elevation"),
        "coletado_em_utc": datetime.now(timezone.utc).isoformat(),
        "fuso_analise": FUSO, "url_consulta": url,
        "documentacao": "https://open-meteo.com/en/docs/historical-weather-api",
    }
    return montar_conjunto(resposta, metadados)


def exportar_json(conjunto: dict) -> bytes:
    """Salva os valores de origem e seus metadados para reabrir sem internet."""
    return json.dumps({"versao": 1, "metadados": conjunto["metadados"],
                       "resposta_api": conjunto["resposta_api"]},
                      ensure_ascii=False, indent=2).encode("utf-8")


def carregar_json(conteudo: bytes):
    """Aceita o formato exportado pelo painel, sem executar conteúdo do arquivo."""
    try:
        arquivo = json.loads(conteudo)
        if not isinstance(arquivo, dict) or arquivo.get("versao") != 1:
            raise ErroDados("Use um JSON exportado por este dashboard (versão 1).")
        meta = arquivo["metadados"]
        if not isinstance(meta, dict) or meta.get("modelo") != "era5":
            raise ErroDados("O arquivo deve identificar o modelo ERA5.")
        return montar_conjunto(arquivo["resposta_api"], meta)
    except (KeyError, TypeError, UnicodeError, ValueError) as erro:
        raise ErroDados(f"Arquivo JSON inválido: {erro}") from erro


def normalizar(texto: str) -> str:
    """Remove acentos só para reconhecer nomes de colunas de diferentes anos."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper().strip()


def ler_inmet(conteudo: bytes):
    """Lê um CSV de estação automática do pacote anual oficial do INMET.

    O cabeçalho de metadados vem antes da tabela; por isso não fixamos o número
    de linhas a pular. A temperatura instantânea é usada na comparação horária.
    A radiação do INMET não é convertida aqui: unidades e intervalos são distintos.
    """
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = conteudo.decode("latin-1")
    linhas = texto.splitlines()
    cabecalho = next((i for i, linha in enumerate(linhas)
                     if normalizar(linha).startswith("DATA") and "HORA" in normalizar(linha)), None)
    if cabecalho is None:
        raise ErroDados("Cabeçalho não encontrado. Envie o CSV de uma estação automática do INMET.")
    metadados = {}
    for linha in linhas[:cabecalho]:
        partes = linha.split(";", 1)
        if len(partes) == 2:
            metadados[partes[0].strip(": ")] = partes[1].strip()
    try:
        original = pd.read_csv(StringIO("\n".join(linhas[cabecalho:])),
                               sep=";", decimal=",", dtype=str)
        nomes = {normalizar(str(coluna)): coluna for coluna in original.columns}
        data_col = next(v for k, v in nomes.items() if k.startswith("DATA"))
        hora_col = next(v for k, v in nomes.items() if "HORA" in k and "UTC" in k)
        temp_col = next(v for k, v in nomes.items()
                        if "TEMPERATURA DO AR" in k and "BULBO SECO" in k)
        # 0000 UTC, 00:00 e 0000 são exemplos comuns nos arquivos anuais.
        hora = original[hora_col].str.extract(r"^(\d{2})", expand=False)
        datas = pd.to_datetime(original[data_col], format="mixed", errors="coerce")
        instantes = (datas + pd.to_timedelta(pd.to_numeric(hora, errors="coerce"), unit="h")).dt.tz_localize("UTC")
        valores = pd.to_numeric(original[temp_col].str.replace(",", ".", regex=False), errors="coerce")
        tabela = pd.DataFrame({"temperatura_inmet_c": valores.to_numpy()}, index=instantes)
    except (StopIteration, ValueError, TypeError, pd.errors.ParserError) as erro:
        raise ErroDados("Não reconheci as colunas DATA, HORA UTC e TEMPERATURA DO AR - BULBO SECO.") from erro
    datas_invalidas = int(tabela.index.isna().sum())
    tabela = tabela.loc[tabela.index.notna()]
    duplicatas = int(tabela.index.duplicated().sum())
    tabela = tabela.loc[~tabela.index.duplicated(keep="first")].sort_index()
    # -9999 e extremos inconsistentes viram lacunas, jamais zero.
    tabela["temperatura_inmet_c"] = tabela.temperatura_inmet_c.where(
        tabela.temperatura_inmet_c.between(-90, 65))
    if not tabela.temperatura_inmet_c.notna().any():
        raise ErroDados("O CSV não contém temperaturas válidas.")
    metadados["linhas_com_data_invalida"] = datas_invalidas
    metadados["horarios_duplicados_removidos"] = duplicatas
    return tabela, metadados
