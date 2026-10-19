"""Texto compartilhado pela interface e pela documentação para evitar divergências.

Este módulo contém apenas conteúdo e caminhos; não consulta nem altera os dados.
"""
from pathlib import Path

IMAGEM_ARQUITETURA = Path(__file__).parent / "assets" / "arquitetura_projeto.png"
INTRODUCAO = (
    "O projeto é uma aplicação monolítica modular em Python: a interface Streamlit, "
    "a coleta e as análises executam no mesmo processo, com responsabilidades separadas "
    "em arquivos. O navegador apresenta o painel e envia as interações; os módulos Python "
    "processam os dados com Pandas. A API REST consumida é externa, do Open-Meteo. "
    "O projeto não expõe uma API REST própria nem utiliza banco de dados."
)
REQUISICOES = (
    "Na carga inicial, o sistema prioriza o JSON salvo. Se ele não existir, o servidor "
    "Python envia uma requisição HTTPS GET ao endpoint /v1/archive do Open-Meteo, "
    "com coordenadas, período, modelo ERA5 e variáveis na URL; a resposta retorna em JSON. "
    "Os dados INMET entram por CSVs baixados pelo usuário, sem requisição automática à sua API."
)
ETL = (
    "O fluxo segue um ETL em memória: extrair o JSON ou os CSVs; transformar campos, "
    "unidades, datas, cobertura e duplicatas; carregar DataFrames tratados para os cálculos "
    "e a visualização. A carga não ocorre em um data warehouse. Os scripts auxiliares "
    "geram arquivos persistentes quando executados; o dashboard reutiliza sessão e cache."
)
FUNCIONAIS = [
    ("RF01", "Obter dados", "Ler o JSON ERA5 local ou consultar o Open-Meteo quando ele não existir; ler os CSVs anuais INMET."),
    ("RF02", "Tratar e selecionar", "Validar dados, preservar lacunas, consolidar estações e selecionar referências até 30 km."),
    ("RF03", "Explorar o período", "Filtrar 2021–2025 por ano e ajustar o limiar analítico entre 25 e 40 °C."),
    ("RF04", "Analisar o calor", "Calcular intensidade, frequência, perfil horário, noites, umidade e sequências de calor."),
    ("RF05", "Comparar o entorno", "Comparar ERA5 e estações nas mesmas datas válidas, mantendo as fontes independentes."),
    ("RF06", "Apresentar resultados", "Exibir gráficos, cartões, critérios e limites; gerar relatório e auditorias pelo terminal."),
]
NAO_FUNCIONAIS = [
    ("RNF01", "Qualidade", "Exigir 90% de cobertura diária e noturna de temperatura; não inventar nem interpolar lacunas."),
    ("RNF02", "Rastreabilidade", "Preservar origem, parâmetros, período, fuso e metadados; manter os CSVs originais."),
    ("RNF03", "Eficiência", "Reutilizar sessão e cache para evitar consultas repetidas. Não há meta de latência medida ou SLA."),
    ("RNF04", "Falhas explícitas", "Tratar falhas previstas e mostrar indisponibilidade. Não há retentativa automática contínua."),
    ("RNF05", "Manutenção", "Separar módulos, comentar regras e manter testes. A aplicação depende diretamente de Streamlit e Pandas."),
    ("RNF06", "Clareza", "Usar uma página, unidades e ausência explícitas; distinguir contexto regional de medições locais e de impactos na saúde."),
]
FUTURO = (
    "Requisito futuro do escopo: integrar as medições do Observatório De Olho na Quebrada "
    "e desfechos de saúde e qualidade de vida compatíveis no tempo e no território. "
    "Essa integração não está implementada porque as bases necessárias não estão disponíveis."
)
LIMITE = (
    "Os requisitos acima descrevem o comportamento atual, não uma certificação de qualidade. "
    "A execução é local; autenticação, controle de acesso para dados pessoais e operação "
    "pública com alta disponibilidade não foram implementados."
)
