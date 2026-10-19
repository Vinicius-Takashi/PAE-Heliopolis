"""Contextualiza exposição ao calor sem transformar estações em dados do bairro."""
import pandas as pd
import streamlit as st

from analise import indicadores_diarios
from inmet_local import manifesto, tratar


@st.cache_data(show_spinner="Organizando o contexto regional…")
def referencias(arquivos):
    return tratar(arquivos)


def comparar_exposicao(horarios, limiar):
    """Compara frequência de calor somente em dias válidos nas três fontes.

    Usar as mesmas datas evita que uma estação com falhas no verão pareça
    artificialmente mais fria. Não usamos essas diferenças para corrigir o bairro.
    """
    series, catalogo, _, _ = referencias(manifesto())
    if catalogo.empty:
        st.caption("Referências INMET indisponíveis para contextualizar o calor regional.")
        return
    indicadores = {"ERA5 · entorno de Heliópolis": indicadores_diarios(horarios, limiar)}
    distancias = {}
    for _, estacao in catalogo.iterrows():
        fonte = series[estacao.referencia].reindex(horarios.index).rename(
            columns={"temperatura_inmet_c": "temperatura_c"})
        # As colunas auxiliares são ausentes, nunca preenchidas pela reanálise.
        for coluna in ["umidade_pct", "vento_ms", "radiacao_wm2", "precipitacao_mm"]:
            fonte[coluna] = float("nan")
        nome = f"{estacao.estacao} · {estacao.codigo}"
        indicadores[nome] = indicadores_diarios(fonte, limiar)
        distancias[nome] = estacao.distancia_km
    validos = pd.concat({nome: dados.dia_valido for nome, dados in indicadores.items()}, axis=1).all(axis=1)
    total = int(validos.sum())
    if not total:
        st.info("Não há dias válidos em comum entre as referências neste período.")
        return
    linhas = []
    for nome, dados in indicadores.items():
        amostra = dados.loc[validos]
        linhas.append({"Referência": nome,
            "Dias com máxima ≥ limiar (%)": 100 * amostra.dia_quente.mean(),
            "Dias válidos em comum": total,
            "Dias válidos na fonte": int(dados.dia_valido.sum()),
            "Distância ao ponto do projeto (km)": distancias.get(nome, float("nan"))})
    st.dataframe(pd.DataFrame(linhas).round(1), hide_index=True, width="stretch")
    st.caption(f"Comparação nas mesmas {total} datas, com pelo menos 90% das horas de temperatura em cada fonte. "
               "Máximas calculadas dos registros horários. INMET: referências até 30 km, sem correção por distância. "
               "Diferenças descrevem contextos distintos; não medem o excesso de calor dentro da comunidade.")
