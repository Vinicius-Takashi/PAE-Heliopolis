"""Formatação compartilhada dos indicadores do painel."""
import pandas as pd


def numero(valor, casas=1, sufixo=""):
    """Ausência aparece como travessão; zero continua sendo um resultado válido."""
    if pd.isna(valor):
        return "—"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".") + sufixo
