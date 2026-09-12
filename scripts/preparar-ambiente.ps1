$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pythonLauncher) {
    & py -3.11 -m venv .venv
} else {
    $python = Get-Command python -ErrorAction Stop
    & $python.Source -m venv .venv
}

$venvPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -e '.[dev]'

[Environment]::SetEnvironmentVariable('PENDENCIAS_RECEITA_REPO', $repoRoot, 'User')
Write-Host ''
Write-Host '[OK] Ambiente Python preparado.' -ForegroundColor Green
Write-Host "Repositorio registrado em PENDENCIAS_RECEITA_REPO=$repoRoot"
Write-Host 'O worker da Receita usara o Chrome ja preparado via CDP; nao e necessario instalar outro navegador do Playwright.'
