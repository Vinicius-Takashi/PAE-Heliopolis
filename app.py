"""Inicia o dashboard: python -m streamlit run app.py.

Este é o ponto de partida do programa: ele só chama a função main() do arquivo
painel.py, que monta a página. Não há cálculo nem coleta de dados aqui.
"""
import sys

# No Windows, silencia o erro cosmético ConnectionResetError (WinError 10054) do asyncio
# quando o usuário atualiza (F5) ou fecha abas do navegador.
if sys.platform == "win32":
    import asyncio
    from asyncio.proactor_events import _ProactorBasePipeTransport

    _antigo_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

    def _silenciar_connection_lost(self, exc=None):
        try:
            _antigo_call_connection_lost(self, exc)
        except (ConnectionResetError, OSError):
            pass

    _ProactorBasePipeTransport._call_connection_lost = _silenciar_connection_lost

from painel import main

if __name__ == "__main__":
    main()
