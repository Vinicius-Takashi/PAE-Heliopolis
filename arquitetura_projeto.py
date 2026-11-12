"""Texto compartilhado pela interface e pela documentação para evitar divergências.

Este módulo contém apenas conteúdo e caminhos; não consulta nem altera os dados.
"""
from pathlib import Path

IMAGEM_ARQUITETURA = Path(__file__).parent / "assets" / "arquitetura_projeto.png"

DIAGRAMA_MERMAID = """
flowchart TD
    subgraph FONTES["🌐 1. Fontes de Dados Externas e Locais"]
        direction LR
        S_UNAS["📍 Sensores Físicos Locais (UNAS)<br/>• 5 Dataloggers (COHAB, Jhorman, Lagoa, etc.)<br/>• Leituras a cada 10 min (CSV Latin-1)"]
        API_METEO["🌐 APIs Gratuitas (Open-Meteo)<br/>• Modelos ERA5, ERA5-Land, ECMWF IFS<br/>• Histórico (5 anos) e previsão via REST JSON"]
        UPLOAD_USR["📂 Upload de Arquivos do Usuário<br/>• Formatos CSV, Excel (.xlsx) e JSON<br/>• Séries temporais personalizadas"]
        SUS_DATA["🏥 Microdados de Saúde (DATASUS)<br/>• Internações SIH/SUS (São Paulo - Capital)<br/>• Doenças Cardiovasculares e Respiratórias"]
    end

    subgraph INGESTAO["⚙️ 2. Camada de Ingestão e Extração"]
        direction LR
        MOD_SENSORES["sensores_locais.py<br/>• Reamostragem horária dos 10 min<br/>• Agregação diária por ponto<br/>• Média conjunta dos 5 locais"]
        MOD_GERENCIADOR["gerenciador_fontes.py<br/>• Conector multi-API Open-Meteo<br/>• Parser inteligente de CSV/Excel<br/>• Detecção automática de colunas"]
        MOD_DADOS["dados.py<br/>• Pipeline de consulta HTTP / Open-Meteo<br/>• Validação de limites físicos e qualidade<br/>• Cache em disco (heliopolis_open_meteo.json)"]
        MOD_SAUDE_ETL["saude.py (Ingestão)<br/>• Leitura de internacoes_diarias_sp.csv<br/>• Filtro por grupos CID-10 e faixas etárias (65+)"]
    end

    subgraph ANALISE["🔬 3. Processamento Analítico e Estatístico"]
        direction LR
        ETL_CLEAN["dados.limpar_horarios()<br/>• Preenchimento da grade horária UTC<br/>• Verificação de completude mínima (90%)<br/>• Preservação de lacunas sem interpolação"]
        ESTAT_METEO["analise.py<br/>• Cálculo de indicadores diários (máx, média, mín)<br/>• Indicadores noturnos (22h–05h59)<br/>• Detecção de sequências de calor contínuas<br/>• Perfil médio horário e correlação calor-umidade"]
        ESTAT_SAUDE["saude.py (Cálculo Epidemiológico)<br/>• Comparação com esperado (mesmo mês e dia)<br/>• Estimativa de Intervalo de Confiança de 95%<br/>• Bootstrap com 2.000 repetições<br/>• Distribuição por faixas térmicas"]
        INTERP["interpretacao.py<br/>• Textos explicativos dinâmicos em linguagem simples<br/>• Ajuste textual contextual segundo a fonte ativa"]
    end

    subgraph UI["💻 4. Camada de Apresentação (Streamlit)"]
        direction LR
        APP["app.py / painel.py<br/>• Ponto de entrada do dashboard web<br/>• Gerenciamento de estado de sessão (st.session_state)"]
        CONTROLES["Controles do Usuário<br/>• Seletor em abas da fonte de dados<br/>• Seletor de período e ano<br/>• Slider de limiar térmico adaptativo (20 °C a 40 °C)"]
        VISUAL["Visualizações e Gráficos (Altair)<br/>• Cartões de métricas em tempo real<br/>• Séries temporais térmicas e noturnas<br/>• Gráficos de barras de internações hospitalares<br/>• Diagrama de dispersão e tabelas interativas"]
    end

    S_UNAS --> MOD_SENSORES
    API_METEO --> MOD_GERENCIADOR
    API_METEO --> MOD_DADOS
    UPLOAD_USR --> MOD_GERENCIADOR
    SUS_DATA --> MOD_SAUDE_ETL

    MOD_SENSORES --> ETL_CLEAN
    MOD_GERENCIADOR --> ETL_CLEAN
    MOD_DADOS --> ETL_CLEAN

    ETL_CLEAN --> ESTAT_METEO
    ESTAT_METEO --> ESTAT_SAUDE
    MOD_SAUDE_ETL --> ESTAT_SAUDE

    ESTAT_METEO --> INTERP
    ESTAT_SAUDE --> INTERP

    ESTAT_METEO --> APP
    ESTAT_SAUDE --> APP
    INTERP --> APP

    APP --> CONTROLES
    CONTROLES -.->|Recalcula dinamicamente| ESTAT_METEO
    CONTROLES -.->|Recalcula dinamicamente| ESTAT_SAUDE
    APP --> VISUAL
"""
INTRODUCAO = (
    "O projeto é uma aplicação monolítica modular em Python: a interface Streamlit, "
    "a coleta e as análises executam no mesmo processo, com responsabilidades separadas "
    "em arquivos. O navegador apresenta o painel e envia as interações; os módulos Python "
    "processam os dados com Pandas. A API REST consumida é externa, do Open-Meteo. "
    "Os dados de saúde vêm de uma tabela local de internações do SIH/SUS, preparada fora do "
    "dashboard. O projeto não expõe uma API REST própria nem utiliza banco de dados."
)
REQUISICOES = (
    "Na carga inicial, o sistema prioriza o JSON salvo. Se ele não existir, o servidor "
    "Python envia uma requisição HTTPS GET ao endpoint /v1/archive do Open-Meteo, "
    "com coordenadas, período, modelo ERA5 e variáveis na URL; a resposta retorna em JSON. "
    "O Open-Meteo é a única fonte meteorológica consumida pela aplicação. O dashboard não "
    "consulta o DATASUS: a tabela de internações é lida do disco."
)
ETL = (
    "O fluxo segue um ETL em memória: extrair o JSON local ou recebido da API; transformar campos, "
    "unidades, datas, cobertura e duplicatas; carregar DataFrames tratados para os cálculos "
    "e a visualização. A carga não ocorre em um data warehouse. Os scripts auxiliares "
    "geram arquivos persistentes quando executados; o dashboard reutiliza sessão e cache. "
    "As internações seguem um caminho separado: scripts em exploracao_saude/ baixam o SIH/SUS, "
    "reduzem os arquivos a contagens e exportam dados_saude/internacoes_diarias_sp.csv."
)
FUNCIONAIS = [
    ("RF01", "Obter dados", "Ler o JSON ERA5 local ou consultar o Open-Meteo quando ele não existir."),
    ("RF02", "Tratar a série", "Validar campos e unidades, organizar a grade horária, remover duplicatas e preservar lacunas."),
    ("RF03", "Explorar o período", "Filtrar o período disponível por ano e ajustar o limiar analítico entre 20 e 40 °C."),
    ("RF04", "Analisar o calor", "Calcular intensidade, frequência, perfil horário, noites, umidade e sequências de calor."),
    ("RF05", "Comparar calor e internações", "Comparar as internações por doenças do coração e respiratórias nos dias quentes e em cada faixa de temperatura com o esperado, com intervalo de 95%."),
    ("RF06", "Apresentar resultados", "Exibir gráficos, cartões, critérios e limites; gerar relatório e auditorias pelo terminal."),
]
NAO_FUNCIONAIS = [
    ("RNF01", "Qualidade", "Exigir 90% de cobertura diária e noturna de temperatura; não inventar nem interpolar lacunas."),
    ("RNF02", "Rastreabilidade", "Preservar a resposta JSON de origem, os parâmetros, o período, o fuso e os metadados da coleta."),
    ("RNF03", "Eficiência", "Reutilizar sessão e cache para evitar consultas repetidas. Não há meta de latência medida ou SLA."),
    ("RNF04", "Falhas explícitas", "Tratar falhas previstas e mostrar indisponibilidade. Não há retentativa automática contínua."),
    ("RNF05", "Manutenção", "Separar módulos, comentar regras e manter testes. A aplicação depende diretamente de Streamlit e Pandas."),
    ("RNF06", "Clareza", "Usar uma página, unidades e ausência explícitas; distinguir contexto regional de medições locais e de impactos na saúde."),
]
FUTURO = (
    "Etapa atual do estudo: relacionar as condições regionais estimadas por ERA5 a dados "
    "de saúde. Já está integrada uma tabela de internações do SIH/SUS da cidade de São Paulo "
    "inteira (não do bairro). Dados de qualidade de vida e do próprio território de Heliópolis "
    "ainda não estão integrados à aplicação."
)
LIMITE = (
    "Os requisitos acima descrevem o comportamento atual, não uma certificação de qualidade. "
    "A execução é local; autenticação, controle de acesso para dados pessoais e operação "
    "pública com alta disponibilidade não foram implementados."
)
