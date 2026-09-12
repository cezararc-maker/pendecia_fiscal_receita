param([Parameter(Mandatory=$true)][string]$QueuePath)

$ErrorActionPreference = 'Stop'
$queue = Get-Content -LiteralPath $QueuePath -Raw | ConvertFrom-Json
$executionFolder = Split-Path -Parent $QueuePath
$type = ([string]$queue.tipo).ToUpperInvariant()
$validationMarker = Join-Path $PSScriptRoot 'modo-validacao-uma-empresa.flag'

function Write-FatalProgress([string]$Stage, [string]$Message) {
    $state = [ordered]@{
        status='ERRO_FATAL'; percent=0; currentCode=''; currentName='';
        stage=$Stage; completed=0; total=@($queue.empresas).Count;
        successful=0; withoutAuthorization=0; errors=1;
        message=$Message; elapsedTime='00:00:00'; estimatedRemaining='00:00:00'
    }
    $state | ConvertTo-Json | Set-Content -LiteralPath $queue.progressPath -Encoding UTF8
    $state.GetEnumerator() | ForEach-Object { $_.Key + '=' + $_.Value } |
        Set-Content -LiteralPath $queue.progressTextPath -Encoding UTF8
}

if ($type -ne 'RECEITA') {
    $legacy = Join-Path $PSScriptRoot 'iniciar-consulta-node.ps1'
    if (-not (Test-Path -LiteralPath $legacy)) {
        Write-FatalProgress 'Worker legado nao encontrado' 'O fluxo nao-Receita foi preservado, mas o iniciar-consulta-node.ps1 nao foi encontrado.'
        exit 2
    }
    & $legacy -QueuePath $QueuePath
    exit $LASTEXITCODE
}

if (Test-Path -LiteralPath $validationMarker) {
    $companies = @($queue.empresas)
    if ($companies.Count -ne 1) {
        Write-FatalProgress `
            'Modo de validacao: fila bloqueada' `
            "O primeiro teste permite exatamente 1 empresa. A fila atual contem $($companies.Count). Selecione somente um CNPJ e tente novamente."
        exit 6
    }

    $onlyCompany = $companies[0]
    $identifierType = ([string]$onlyCompany.tipoIdentificador).ToUpperInvariant()
    $identifier = ([string]$onlyCompany.identificador) -replace '\D', ''
    if ($identifierType -ne 'CNPJ' -or $identifier.Length -ne 14) {
        Write-FatalProgress `
            'Modo de validacao: empresa nao elegivel' `
            'O primeiro teste permite somente uma empresa identificada como CNPJ com 14 digitos.'
        exit 7
    }
}

try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:9225/json/version' -TimeoutSec 2 | Out-Null
} catch {
    Write-FatalProgress 'Navegador nao preparado' 'Use o botao Preparar navegador e conclua o login no Portal da Receita.'
    exit 2
}

$repoRoot = [Environment]::GetEnvironmentVariable('PENDENCIAS_RECEITA_REPO', 'User')
if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    $repoRoot = Join-Path ([Environment]::GetFolderPath('Desktop')) 'GitHub\Pendências Fiscais Receita'
}
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-FatalProgress 'Ambiente Python nao preparado' "Execute scripts\preparar-ambiente.ps1 no repositorio: $repoRoot"
    exit 3
}

$stdout = Join-Path $executionFolder 'worker-python.stdout.log'
$stderr = Join-Path $executionFolder 'worker-python.stderr.log'
$arguments = '-m receita_automacao.queue_worker --queue "' + $QueuePath + '"'
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $repoRoot `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
$process.Id | Set-Content -LiteralPath (Join-Path $executionFolder 'worker.pid') -Encoding ASCII
