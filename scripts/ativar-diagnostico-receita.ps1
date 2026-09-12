param(
    [Parameter(Mandatory=$true)]
    [string]$WorkbookPath,

    [Parameter(Mandatory=$true)]
    [ValidateSet('connected-only', 'after-open', 'after-cnpj', 'after-procurador', 'full')]
    [string]$Stage
)

$ErrorActionPreference = 'Stop'
$workbook = (Resolve-Path -LiteralPath $WorkbookPath).Path
$workbookFolder = Split-Path -Parent $workbook
$automationDir = Join-Path $workbookFolder 'Pendencias Fiscais\automacao'
$marker = Join-Path $automationDir 'diagnostico-receita.flag'

if (-not (Test-Path -LiteralPath $automationDir)) {
    throw "Pasta de automacao nao encontrada: $automationDir"
}

$Stage | Set-Content -LiteralPath $marker -Encoding ASCII

Write-Host ''
Write-Host '[OK] Diagnostico da Receita ativado.' -ForegroundColor Green
Write-Host "Etapa: $Stage"
Write-Host 'Enquanto o diagnostico estiver ativo, a fila da Receita deve conter exatamente 1 CNPJ.' -ForegroundColor Yellow
if ($Stage -eq 'connected-only') {
    Write-Host 'O Python apenas se conectara ao Chrome. Faca toda a representacao manualmente.'
} elseif ($Stage -eq 'after-open') {
    Write-Host 'O Python apenas abrira o menu de representacao. Preencha CNPJ + Procurador + Representar manualmente.'
} elseif ($Stage -eq 'after-cnpj') {
    Write-Host 'O Python preenchera o CNPJ e aguardara voce concluir Procurador + Representar manualmente.'
} elseif ($Stage -eq 'after-procurador') {
    Write-Host 'O Python preenchera o CNPJ, selecionara Procurador e aguardara voce clicar Representar manualmente.'
} else {
    Write-Host 'O Python executara o fluxo automatico completo, mas limitado a exatamente 1 CNPJ.'
}
Write-Host "Marcador: $marker"
