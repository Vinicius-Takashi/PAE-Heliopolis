"""Análise exploratória de exposição ao calor no contexto de Heliópolis.

Não há medições locais ou desfechos de saúde integrados. As referências
regionais descrevem o ambiente e não são atribuídas às casas ou moradores.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from analise import episodios_quentes, indicadores_diarios, indicadores_noturnos, resumo_anual
from apoio import numero
from arquitetura_projeto import (INTRODUCAO, REQUISICOES, ETL, FUNCIONAIS,
    NAO_FUNCIONAIS, FUTURO, LIMITE, IMAGEM_ARQUITETURA)
from dados import (ErroDados, FIM_ESTUDO, FUSO, INICIO_ESTUDO,
                   buscar_open_meteo, carregar_json, recortar_periodo)

BASE_LOCAL = Path(__file__).parent / "dados_locais" / "heliopolis_open_meteo.json"
COBERTURA = 0.90
MINIMO_DIAS = 3


@st.cache_data(ttl=86400, max_entries=6, show_spinner=False)
def carregar_online(inicio, fim):
    return buscar_open_meteo(inicio, fim)


def iniciar_base():
    """A coleta acontece sem expor operações de manutenção ao leitor."""
    try:
        if "conjunto" in st.session_state:
            st.session_state["conjunto"] = recortar_periodo(st.session_state["conjunto"])
        elif not st.session_state.get("carga_inicial_tentada"):
            st.session_state["carga_inicial_tentada"] = True
            conjunto = carregar_json(BASE_LOCAL.read_bytes()) if BASE_LOCAL.is_file() else carregar_online(INICIO_ESTUDO, FIM_ESTUDO)
            st.session_state["conjunto"] = recortar_periodo(conjunto)
    except (ErroDados, OSError) as erro:
        st.session_state.pop("conjunto", None)
        st.session_state["erro_inicial"] = str(erro)


def recortar_base(conjunto, ano):
    """Todas as perguntas da página usam o mesmo recorte temporal."""
    if ano == "Todo o período":
        return conjunto
    local = conjunto["horarios"].index.tz_convert(FUSO)
    datas = local[local.year == int(ano)]
    return recortar_periodo(conjunto, datas.min().date(), datas.max().date())


def mostrar_exposicao(diario, noites, episodios, limiar):
    validos = int(diario.dia_valido.sum())
    quentes = int(diario.dia_quente.sum()) if validos else float("nan")
    cartoes = st.columns(4)
    cartoes[0].metric("Maior temperatura horária", numero(diario.temp_max_c.max(), sufixo=" °C"))
    cartoes[1].metric(f"Dias com máxima ≥ {limiar:g} °C", numero(quentes, 0))
    cartoes[2].metric("Sequências de calor", numero(len(episodios) if validos else float("nan"), 0))
    cartoes[3].metric("Temperatura média noturna", numero(noites.temp_noturna_media_c.mean(), sufixo=" °C"))
    st.caption(f"Contexto regional ERA5 · {validos:,} de {len(diario):,} dias válidos · "
               f"{int(noites.noite_valida.sum()):,} noites válidas · sequências de pelo menos três dias com máxima ≥ limiar.")
    if not validos:
        st.warning("Dados insuficientes para analisar a exposição diária neste período.")
    esquerda, direita = st.columns([2, 1])
    with esquerda, st.container(border=True):
        st.markdown("**Temperatura ao longo do tempo**")
        serie = diario[["temp_max_c", "temp_media_c", "temp_min_c"]]
        # A agregação mensal facilita ler os cinco anos. Os cartões e episódios
        # continuam usando os valores diários, preservando os extremos.
        longo = len(diario) > 370
        if longo:
            serie = serie.resample("MS").mean()
        st.line_chart(serie.rename(columns={"temp_max_c": "Máxima (°C)",
            "temp_media_c": "Média (°C)", "temp_min_c": "Mínima (°C)"}),
            color=["#d94832", "#d99b25", "#287b9c"], height=240)
        st.caption(("Médias mensais das máximas, médias e mínimas diárias. " if longo else
                    "Máximas, médias e mínimas dos registros horários de cada dia. ") +
                   "Permite explorar a intensidade e a sazonalidade do calor regional.")
    with direita, st.container(border=True):
        st.markdown("**Frequência de dias quentes**")
        anual = resumo_anual(diario)
        visual = anual[["dias_quentes_pct"]].rename(columns={"dias_quentes_pct": "Dias com calor (%)"})
        visual.index = visual.index.astype(str)
        st.bar_chart(visual, color="#dc8532", height=240)
        st.caption("Percentual dos dias válidos com máxima ≥ limiar. Comparação descritiva entre anos; cinco anos não estabelecem uma tendência climática.")


def mostrar_rotina(horarios, diario, noites):
    """Descreve o ambiente térmico, sem substituir observações de sono ou sintomas."""
    hora_col, noite_col, umidade_col = st.columns(3)
    local = horarios.tz_convert(FUSO)
    with hora_col, st.container(border=True):
        st.markdown("**Calor por horário**")
        perfil = local.temperatura_c.groupby(local.index.hour).mean()
        perfil.index.name = "Hora de São Paulo"
        st.line_chart(perfil.rename("Temperatura (°C)"), color="#d99b25", height=220)
        st.caption("Temperatura média em cada hora do dia. Ajuda a identificar os horários de maior calor no contexto da rotina dos moradores.")
    with noite_col, st.container(border=True):
        st.markdown("**Temperatura à noite**")
        serie = noites[["temp_noturna_media_c"]].rename(columns={"temp_noturna_media_c": "Temperatura noturna (°C)"})
        if len(serie) > 370:
            serie = serie.resample("MS").mean()
            legenda = "Médias mensais das noites válidas"
        else:
            legenda = "Médias das noites válidas"
        st.line_chart(serie, color="#287b9c", height=220)
        st.caption(legenda + " · 22h–05h59. Caracteriza o período de descanso, sem medir a qualidade do sono.")
    with umidade_col, st.container(border=True):
        st.markdown("**Calor e umidade**")
        # Cada ponto é um dia com cobertura suficiente nas duas variáveis.
        # Mostramos todo o conjunto para explorar a relação, sem selecionar
        # apenas dias quentes e esconder o restante da distribuição.
        pontos = diario.loc[diario.dia_valido, ["temp_media_c", "umidade_pct"]].dropna().rename(
            columns={"temp_media_c": "Temperatura (°C)", "umidade_pct": "Umidade (%)"})
        if pontos.empty:
            st.info("Não há dias com cobertura suficiente de temperatura e umidade neste recorte.")
        else:
            st.scatter_chart(pontos, x="Temperatura (°C)", y="Umidade (%)", color="#287b9c", height=220)
            st.caption("Cada ponto representa as médias de um dia. Explora a relação entre calor e umidade; não é sensação térmica nem índice de estresse térmico.")


def mostrar_persistencia(episodios, limiar):
    st.markdown("**Quando o calor persistiu por vários dias?**")
    if episodios.empty:
        st.write("Nenhuma sequência de três dias ou mais identificada neste recorte.")
    else:
        tabela = episodios.sort_values(["duracao_dias", "inicio"], ascending=[False, True]).copy()
        tabela["inicio"] = tabela.inicio.dt.strftime("%d/%m/%Y")
        tabela["fim"] = tabela.fim.dt.strftime("%d/%m/%Y")
        tabela = tabela.rename(columns={"inicio": "Início", "fim": "Fim", "duracao_dias": "Duração (dias)",
            "maior_temperatura_c": "Maior temperatura (°C)", "media_das_maximas_c": "Média das máximas (°C)",
            "toca_borda_da_consulta": "Pode continuar fora do recorte"})
        st.dataframe(tabela.round(1), hide_index=True, width="stretch")
    st.caption(f"Máxima ≥ {limiar:g} °C em pelo menos três dias consecutivos; dias inválidos interrompem a sequência. "
               "Critério exploratório, não uma definição oficial de onda de calor.")


def mostrar_arquitetura():
    """Apresenta os requisitos e o fluxo técnico antes das análises do estudo."""
    st.subheader("Engenharia de software e arquitetura")
    st.write(INTRODUCAO)
    st.image(str(IMAGEM_ARQUITETURA), caption="Arquitetura implementada: API REST externa, ETL em memória e apresentação no Streamlit.")
    st.write(REQUISICOES)
    st.write(ETL)
    funcionais, qualidade = st.columns(2)
    with funcionais:
        st.markdown("**Requisitos funcionais — o que o sistema faz**")
        for codigo, titulo, descricao in FUNCIONAIS:
            st.markdown(f"**{codigo} · {titulo}:** {descricao}")
    with qualidade:
        st.markdown("**Requisitos não funcionais — como o sistema deve operar**")
        for codigo, titulo, descricao in NAO_FUNCIONAIS:
            st.markdown(f"**{codigo} · {titulo}:** {descricao}")
    st.caption(FUTURO)
    st.caption(LIMITE)


def main():
    st.set_page_config(page_title="Heliópolis | Estresse térmico", page_icon="☀️", layout="wide")
    st.title("Heliópolis · Estresse térmico")
    st.write("Análise exploratória da exposição ao calor para o estudo da saúde e da qualidade de vida dos moradores.")
    st.caption("2021–2025 · Contexto ambiental regional de Heliópolis")
    mostrar_arquitetura()
    st.info("Análise preliminar: as medições do Observatório De Olho na Quebrada não estão disponíveis para o projeto. "
            "Sem essa base e sem desfechos de saúde ou qualidade de vida integrados, os resultados descrevem "
            "o calor regional; não medem impactos nos moradores nem temperaturas dentro das moradias.")
    iniciar_base()
    if "conjunto" not in st.session_state:
        st.error("A série ambiental está indisponível. Não é possível apresentar a análise neste momento.")
        return
    original = st.session_state["conjunto"]
    filtro, criterio = st.columns(2)
    with filtro:
        anos = original["horarios"].index.tz_convert(FUSO).year.unique()
        opcoes = ["Todo o período", *map(str, sorted(anos))]
        if st.session_state.get("periodo", opcoes[0]) not in opcoes:
            st.session_state["periodo"] = opcoes[0]
        ano = st.selectbox("Período", opcoes, key="periodo")
    with criterio:
        limiar = st.slider("Temperatura de referência para explorar o calor (°C)", 25.0, 40.0, 30.0, 0.5, key="limiar")
    conjunto = recortar_base(original, ano)
    horarios = conjunto["horarios"]
    diario = indicadores_diarios(horarios, limiar, COBERTURA)
    noites = indicadores_noturnos(horarios, COBERTURA)
    episodios = episodios_quentes(diario, MINIMO_DIAS)
    inicio = date.fromisoformat(conjunto["metadados"]["inicio"]).strftime("%d/%m/%Y")
    fim = date.fromisoformat(conjunto["metadados"]["fim"]).strftime("%d/%m/%Y")
    st.caption(f"{inicio} a {fim} · A referência selecionada é um limiar analítico, não um limite de risco à saúde.")
    mostrar_exposicao(diario, noites, episodios, limiar)
    mostrar_rotina(horarios, diario, noites)
    with st.expander("Explorar sequências de calor persistente"):
        mostrar_persistencia(episodios, limiar)
    st.caption("Leitura dos resultados: dias e noites exigem pelo menos 90% das horas de temperatura; "
               "noites parciais são excluídas. Máximas vêm de amostras horárias. Lacunas permanecem ausentes. "
               "ERA5 representa uma grade regional (~25 km), não medições dentro de Heliópolis.")
    st.caption("Fonte meteorológica: [Open-Meteo / Copernicus ERA5](https://open-meteo.com/en/docs/historical-weather-api).")


if __name__ == "__main__":
    main()
