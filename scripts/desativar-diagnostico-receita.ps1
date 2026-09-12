param(
    [Parameter(Mandatory=$true)]
    [string]$WorkbookPath
)

$ErrorActionPreference = 'Stop'
$workbook = (Resolve-Path -LiteralPath $WorkbookPath).Path
$workbookFolder = Split-Path -Parent $workbook
$automationDir = Join-Path $workbookFolder 'Pendencias Fiscais\automacao'
$marker = Join-Path $automationDir 'diagnostico-receita.flag'

if (-not (Test-Path -LiteralPath $automationDir)) {
    throw "Pasta de automacao nao encontrada: $automationDir"
}

if (Test-Path -LiteralPath $marker) {
    Remove-Item -LiteralPath $marker -Force
    Write-Host '[OK] Diagnostico da Receita desativado.' -ForegroundColor Green
} else {
    Write-Host 'O diagnostico da Receita ja estava desativado.' -ForegroundColor Yellow
}

Write-Host 'A proxima consulta usara o fluxo normal configurado na integracao.'
