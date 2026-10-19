"""Referências regionais do INMET: arquivos originais permanecem intocados.

Distância não permite converter uma estação em um termômetro de Heliópolis.
Por isso mantemos cada estação separada, sem interpolação ou correção de viés.
"""
from pathlib import Path
from math import radians, sin, cos, asin, sqrt

import pandas as pd

from dados import (LATITUDE, LONGITUDE, INICIO_ESTUDO, FIM_ESTUDO, FUSO,
                   ErroDados, grade_horaria, ler_inmet, normalizar)

PASTA = Path(__file__).resolve().parent / "dados_locais" / "inmet"
# Recorte operacional para referências metropolitanas, não uma norma INMET.
RAIO_KM = 30.0


def distancia_km(latitude, longitude, referencia_lat=LATITUDE, referencia_lon=LONGITUDE):
    """Distância em linha reta sobre a esfera ao ponto aproximado do projeto."""
    lat1, lat2 = radians(referencia_lat), radians(latitude)
    delta = radians(longitude - referencia_lon)
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta / 2) ** 2
    return 6371.0088 * 2 * asin(sqrt(min(1, max(0, a))))


def manifesto(pasta=PASTA):
    """Tamanho e modificação invalidam o cache quando o usuário troca um CSV."""
    return tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns)
                 for p in sorted(Path(pasta).rglob("*"))
                 if p.is_file() and p.suffix.lower() == ".csv")


def cabecalho(caminho):
    # Só lemos o início dos milhares de arquivos nacionais para localizar estações.
    with open(caminho, "rb") as arquivo:
        bruto = arquivo.read(4096)
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")
    meta = {}
    for linha in texto.splitlines():
        if normalizar(linha).startswith("DATA;"):
            break
        chave, separador, valor = linha.partition(";")
        if separador:
            meta[normalizar(chave).rstrip(": ")] = valor.strip()
    return meta


def tratar(manifest, raio_km=RAIO_KM):
    """Junta anos por código; tolera variação cadastral de até 25 m.

    A grade usa dias locais. Assim, somente as três primeiras horas UTC de
    2026 podem completar o último dia de 2025, sem incluir dias locais de 2026.
    Duplicatas conflitantes viram lacunas, em vez de escolher um valor ao acaso.
    """
    grade = grade_horaria(INICIO_ESTUDO, FIM_ESTUDO)
    grupos, auditoria = {}, []
    for caminho, _, _ in manifest:
        try:
            meta = cabecalho(caminho)
            lat = float(meta["LATITUDE"].replace(",", "."))
            lon = float(meta["LONGITUDE"].replace(",", "."))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Coordenadas inválidas")
            distancia = distancia_km(lat, lon)
            if distancia > raio_km:
                continue
            codigo = meta["CODIGO (WMO)"]
            tabela, qualidade = ler_inmet(Path(caminho).read_bytes())
            tabela = tabela.loc[(tabela.index >= grade[0]) & (tabela.index <= grade[-1])]
            if tabela.empty:
                continue
            # Há pequenas mudanças de precisão cadastral entre os anos. Até
            # 25 m agrupamos pelo código, mas guardamos as coordenadas originais.
            # Isso não comprova ausência de mudanças no entorno ou no instrumento.
            chave = next((k for k, g in grupos.items() if g["codigo"] == codigo
                and distancia_km(lat, lon, g["latitude"], g["longitude"]) <= 0.025),
                f"{codigo} ({lat:.6f}, {lon:.6f})")
            grupo = grupos.setdefault(chave, {"codigo": codigo, "estacao": meta.get("ESTACAO", codigo),
                "latitude": lat, "longitude": lon, "altitude_m": meta.get("ALTITUDE", ""),
                "distancia_km": distancia, "partes": [], "arquivos": []})
            grupo["partes"].append(tabela)
            grupo["arquivos"].append(caminho)
            auditoria.append({"arquivo": caminho, "situacao": "Lido", **qualidade})
        except (OSError, KeyError, ValueError) as erro:
            auditoria.append({"arquivo": caminho, "situacao": str(erro)})
    series, resumo, anuais = {}, [], []
    for chave, grupo in grupos.items():
        valores = pd.concat(grupo.pop("partes"))["temperatura_inmet_c"]
        conflitos = valores.groupby(level=0).nunique().gt(1)
        serie = valores.groupby(level=0).first().mask(conflitos).reindex(grade)
        series[chave] = serie.to_frame()
        resumo.append({"referencia": chave, **grupo,
            "horas_validas": int(serie.notna().sum()), "horas_esperadas": len(grade),
            "cobertura_pct": 100 * serie.notna().mean(),
            "conflitos_entre_arquivos": int(conflitos.sum())})
        for ano, parte in serie.groupby(serie.index.tz_convert(FUSO).year):
            anuais.append({"referencia": chave, "ano": ano, "horas_esperadas": len(parte),
                "horas_validas": int(parte.notna().sum()), "cobertura_pct": 100 * parte.notna().mean()})
    catalogo = pd.DataFrame(resumo)
    if not catalogo.empty:
        catalogo = catalogo.sort_values(["distancia_km", "referencia"]).reset_index(drop=True)
    return series, catalogo, pd.DataFrame(anuais), pd.DataFrame(auditoria)


if __name__ == "__main__":
    series, catalogo, anual, auditoria = tratar(manifesto())
    destino = PASTA.parent / "inmet_tratado"
    destino.mkdir(exist_ok=True)
    for nome, tabela in [("estacoes", catalogo), ("cobertura_anual", anual), ("auditoria", auditoria)]:
        tabela.to_csv(destino / f"{nome}.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
    for posicao, (chave, tabela) in enumerate(series.items()):
        tabela.to_csv(destino / f"{posicao}_{chave.split()[0]}_horario.csv", sep=";", decimal=",", encoding="utf-8-sig")
    print(catalogo.drop(columns=["arquivos"]).to_string(index=False))
    print(anual.to_string(index=False))
