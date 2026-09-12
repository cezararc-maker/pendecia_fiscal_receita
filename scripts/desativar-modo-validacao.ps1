param(
    [Parameter(Mandatory=$true)]
    [string]$WorkbookPath
)

$ErrorActionPreference = 'Stop'
$workbook = (Resolve-Path -LiteralPath $WorkbookPath).Path
$workbookFolder = Split-Path -Parent $workbook
$automationDir = Join-Path $workbookFolder 'Pendencias Fiscais\automacao'
$validationMarker = Join-Path $automationDir 'modo-validacao-uma-empresa.flag'

if (-not (Test-Path -LiteralPath $automationDir)) {
    throw "Pasta de automacao do prototipo nao encontrada: $automationDir"
}

if (Test-Path -LiteralPath $validationMarker) {
    Remove-Item -LiteralPath $validationMarker -Force
    Write-Host '[OK] Modo de validacao de uma empresa desativado.' -ForegroundColor Green
} else {
    Write-Host '[OK] O modo de validacao ja estava desativado.' -ForegroundColor Green
}

Write-Host "Workbook: $workbook"
Write-Host 'A proxima fila da Receita podera conter mais de uma empresa. Use somente apos validar o primeiro teste real.' -ForegroundColor Yellow
