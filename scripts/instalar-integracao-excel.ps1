param(
    [Parameter(Mandatory=$true)]
    [string]$WorkbookPath
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$workbook = (Resolve-Path -LiteralPath $WorkbookPath).Path
$workbookFolder = Split-Path -Parent $workbook
$automationDir = Join-Path $workbookFolder 'Pendencias Fiscais\automacao'

if (-not (Test-Path -LiteralPath $automationDir)) {
    throw "Pasta de automacao do prototipo nao encontrada: $automationDir"
}

$newStart = Join-Path $repoRoot 'integracao_excel\automacao\iniciar-consulta.ps1'
$newStop = Join-Path $repoRoot 'integracao_excel\automacao\parar-consulta.ps1'
$currentStart = Join-Path $automationDir 'iniciar-consulta.ps1'
$currentStop = Join-Path $automationDir 'parar-consulta.ps1'
$legacyStart = Join-Path $automationDir 'iniciar-consulta-node.ps1'

if (-not (Test-Path -LiteralPath $currentStart)) {
    throw "iniciar-consulta.ps1 original nao encontrado em $automationDir"
}

if (-not (Test-Path -LiteralPath $legacyStart)) {
    $currentText = Get-Content -LiteralPath $currentStart -Raw
    if ($currentText -match 'receita_automacao\.queue_worker') {
        throw 'A integracao Python ja parece instalada, mas o backup iniciar-consulta-node.ps1 nao existe. Interrompendo por seguranca.'
    }
    Copy-Item -LiteralPath $currentStart -Destination $legacyStart
}

$backupDir = Join-Path $automationDir ('backup_python_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item -LiteralPath $currentStart -Destination (Join-Path $backupDir 'iniciar-consulta.ps1')
if (Test-Path -LiteralPath $currentStop) {
    Copy-Item -LiteralPath $currentStop -Destination (Join-Path $backupDir 'parar-consulta.ps1')
}

Copy-Item -LiteralPath $newStart -Destination $currentStart -Force
Copy-Item -LiteralPath $newStop -Destination $currentStop -Force
[Environment]::SetEnvironmentVariable('PENDENCIAS_RECEITA_REPO', $repoRoot, 'User')

Write-Host ''
Write-Host '[OK] Integracao da Receita com Python instalada.' -ForegroundColor Green
Write-Host "Workbook preservado: $workbook"
Write-Host "Scripts atualizados em: $automationDir"
Write-Host "Backup desta instalacao: $backupDir"
Write-Host 'O fluxo FGTS continua delegado ao iniciar-consulta-node.ps1 original.'
