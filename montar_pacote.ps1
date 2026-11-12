# montar_pacote.ps1
# Monta o pacote distribuível do app Heliópolis com Python Embeddable.
#
# USO:
#   1. Abra o PowerShell nesta pasta
#   2. Execute:  .\montar_pacote.ps1
#   3. Faça upload do ZIP gerado em Releases no GitHub
#
# O que o script faz:
#   - Baixa o Python 3.12 Embeddable (Windows 64-bit) se ainda não existir
#   - Habilita pip no Python Embeddable
#   - Instala as dependências do requirements.txt dentro dele
#   - Copia os arquivos do projeto para a pasta de saída
#   - Compacta tudo em heliopolis_app.zip

$ErrorActionPreference = "Stop"

$PY_VERSION  = "3.12.10"
$PY_ZIP_URL  = "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-embed-amd64.zip"
$PY_ZIP_FILE = "python-embed.zip"
$DIST_DIR    = "dist\heliopolis_app"
$PY_DIR      = "$DIST_DIR\python"
$OUT_ZIP     = "dist\heliopolis_app.zip"

Write-Host ""
Write-Host "====  Heliópolis · Montador de Pacote  ====" -ForegroundColor Cyan
Write-Host ""

# 1. Cria pasta de saída
if (Test-Path $DIST_DIR) { Remove-Item -Recurse -Force $DIST_DIR }
New-Item -ItemType Directory -Force -Path $DIST_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $PY_DIR   | Out-Null

# 2. Baixa Python Embeddable
if (-not (Test-Path $PY_ZIP_FILE)) {
    Write-Host "[1/5] Baixando Python $PY_VERSION Embeddable..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $PY_ZIP_URL -OutFile $PY_ZIP_FILE -UseBasicParsing
} else {
    Write-Host "[1/5] Python Embeddable já baixado." -ForegroundColor Green
}

Write-Host "[2/5] Extraindo Python Embeddable..." -ForegroundColor Yellow
Expand-Archive -Path $PY_ZIP_FILE -DestinationPath $PY_DIR -Force

# 3. Habilita pip: descomenta "import site" no _pth
$pthFile = Get-ChildItem -Path $PY_DIR -Filter "*._pth" | Select-Object -First 1
if ($pthFile) {
    (Get-Content $pthFile.FullName) -replace "#import site", "import site" |
        Set-Content $pthFile.FullName
    Write-Host "[3/5] pip habilitado no Python Embeddable." -ForegroundColor Green
}

# Baixa e instala pip
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$getPipFile = "$PY_DIR\get-pip.py"
Write-Host "[3/5] Baixando get-pip.py..." -ForegroundColor Yellow
Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipFile -UseBasicParsing
& "$PY_DIR\python.exe" "$getPipFile" --no-warn-script-location -q

# 4. Instala dependências
Write-Host "[4/5] Instalando dependências em python\Scripts..." -ForegroundColor Yellow
& "$PY_DIR\python.exe" -m pip install --no-warn-script-location -q `
    -r "requirements.txt" `
    --target "$PY_DIR\Lib\site-packages"

# 5. Copia arquivos do projeto (exclui pastas desnecessárias)
Write-Host "[5/5] Copiando arquivos do projeto..." -ForegroundColor Yellow
$exclude = @("dist", ".git", "__pycache__", "*.pyc", ".venv", "venv", "node_modules",
             "python-embed.zip", "montar_pacote.ps1", ".deps_ok")

Get-ChildItem -Path "." -Exclude $exclude | ForEach-Object {
    $dest = Join-Path $DIST_DIR $_.Name
    if ($_.PSIsContainer) {
        Copy-Item -Recurse -Force $_.FullName $dest
    } else {
        Copy-Item -Force $_.FullName $dest
    }
}

# Remove __pycache__ da cópia
Get-ChildItem -Path $DIST_DIR -Recurse -Filter "__pycache__" |
    Remove-Item -Recurse -Force

# 6. Compacta
Write-Host "" 
Write-Host "Compactando → $OUT_ZIP ..." -ForegroundColor Yellow
if (Test-Path $OUT_ZIP) { Remove-Item $OUT_ZIP }
Compress-Archive -Path "$DIST_DIR\*" -DestinationPath $OUT_ZIP

$sizeMB = [math]::Round((Get-Item $OUT_ZIP).Length / 1MB, 1)
Write-Host ""
Write-Host "====  Pronto!  ====" -ForegroundColor Green
Write-Host "Arquivo: $OUT_ZIP  ($sizeMB MB)"
Write-Host ""
Write-Host "Próximos passos:"
Write-Host "  1. Teste: extraia o ZIP numa pasta e dê duplo clique em iniciar.bat"
Write-Host "  2. Faça upload do ZIP em: GitHub → seu repo → Releases → New Release"
Write-Host "  3. Cole o link da release no README.md e no texto de envio"
Write-Host ""

