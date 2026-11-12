@echo off
chcp 65001 >nul
title Heliópolis - Estresse Térmico

:: Detecta Python Embeddable na pasta "python\"
:: Se não encontrar, tenta o Python do sistema.

set "BASE=%~dp0"
set "PYEMBED=%BASE%python\python.exe"
set "SCRIPTS=%BASE%python\Scripts"

if exist "%PYEMBED%" (
    set "PYTHON=%PYEMBED%"
    set "PATH=%SCRIPTS%;%BASE%python;%PATH%"
    echo [OK] Usando Python embutido em python\
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo.
        echo ERRO: Python nao encontrado.
        echo Extraia o pacote completo com a pasta python\ incluida.
        echo.
        pause
        exit /b 1
    )
    set "PYTHON=python"
    echo [AVISO] Pasta python\ nao encontrada. Usando Python do sistema.
)

:: Se o Python ja traz as dependencias (pacote do montar_pacote.ps1),
:: pula a instalacao. Assim o painel abre mesmo sem internet.

if not exist "%BASE%.deps_ok" (
    "%PYTHON%" -c "import streamlit, pandas, altair, numpy, requests, openpyxl" >nul 2>&1 && echo ok > "%BASE%.deps_ok"
)

:: Instala dependencias na primeira execucao (so se ainda faltarem)

if not exist "%BASE%.deps_ok" (
    echo.
    echo [1/2] Instalando dependencias...
    "%PYTHON%" -m pip install --no-warn-script-location -q -r "%BASE%requirements.txt"

    if errorlevel 1 (
        echo.
        echo ERRO ao instalar dependencias.
        pause
        exit /b 1
    )

    echo ok > "%BASE%.deps_ok"
    echo [OK] Dependencias instaladas.
)

echo.
echo [2/2] Iniciando o dashboard Heliopolis...
echo Aguarde o navegador abrir em http://localhost:8501
echo.
echo Para encerrar: Ctrl+C
echo.

:: Evita a pergunta "Email:" do Streamlit na primeira execucao
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
    > "%USERPROFILE%\.streamlit\credentials.toml" (
        echo [general]
        echo email = ""
    )
)

"%PYTHON%" -m streamlit run "%BASE%app.py" ^
    --server.headless false ^
    --server.port 8501 ^
    --browser.gatherUsageStats false

pause