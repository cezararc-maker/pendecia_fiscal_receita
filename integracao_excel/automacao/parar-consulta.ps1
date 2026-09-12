param([Parameter(Mandatory=$true)][string]$ExecutionFolder)

$ErrorActionPreference = 'Stop'
$pidPath = Join-Path $ExecutionFolder 'worker.pid'
if (Test-Path -LiteralPath $pidPath) {
    $workerPid = [int](Get-Content -LiteralPath $pidPath -Raw)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$workerPid" -ErrorAction SilentlyContinue
    if ($process) {
        $isPythonWorker = $process.Name -match '^python(?:w)?\.exe$' -and $process.CommandLine -like '*receita_automacao.queue_worker*'
        $isLegacyNode = $process.Name -eq 'node.exe' -and $process.CommandLine -like '*worker.mjs*'
        if ($isPythonWorker -or $isLegacyNode) {
            Stop-Process -Id $workerPid -Force -ErrorAction SilentlyContinue
        }
    }
}

$progressJson = Join-Path $ExecutionFolder 'progresso.json'
$progressText = Join-Path $ExecutionFolder 'progresso.txt'
$state = [ordered]@{
    status='CANCELADO'; percent=0; currentCode=''; currentName='';
    stage='Consulta interrompida pelo usuario'; completed=0; total=0;
    successful=0; withoutAuthorization=0; errors=0;
    message='Os resultados concluidos foram preservados.';
    elapsedTime='00:00:00'; estimatedRemaining='00:00:00'
}
if (Test-Path -LiteralPath $progressJson) {
    try {
        $previous = Get-Content -LiteralPath $progressJson -Raw | ConvertFrom-Json
        foreach ($name in @('percent','currentCode','currentName','completed','total','successful','withoutAuthorization','errors','elapsedTime')) {
            if ($null -ne $previous.$name) { $state[$name] = $previous.$name }
        }
    } catch { }
}
$state.status = 'CANCELADO'
$state.stage = 'Consulta interrompida pelo usuario'
$state.message = 'Os resultados concluidos foram preservados.'
$state.estimatedRemaining = '00:00:00'
$state | ConvertTo-Json | Set-Content -LiteralPath $progressJson -Encoding UTF8
$state.GetEnumerator() | ForEach-Object { $_.Key + '=' + $_.Value } |
    Set-Content -LiteralPath $progressText -Encoding UTF8
