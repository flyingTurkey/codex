param(
    [switch]$PreflightOnly,
    [string]$DataRoot = 'D:\SRBGData'
)

$ErrorActionPreference = 'Stop'
$ES_CONTINUOUS = [uint32]2147483648
$ES_SYSTEM_REQUIRED = [uint32]0x00000001
$reportRoot = Join-Path $DataRoot 'reports'
$requiredDiscoverySetting = 'SRBG_SOURCE_DISCOVERY_ENABLED=false'
$script:disableAiWorker = $false

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class SrbgPowerState {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern uint SetThreadExecutionState(uint flags);
}
'@

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "PILOT_PREFLIGHT_COMMAND_MISSING:$Name"
    }
}

function Invoke-Preflight {
    Assert-Command 'docker'
    if (-not (Test-Path -LiteralPath (Join-Path $DataRoot 'srbg-data.vhdx'))) {
        throw 'PILOT_PREFLIGHT_DATA_VHD_MISSING'
    }
    if ((Get-PSDrive -Name D).Free -lt 20GB) {
        throw 'PILOT_PREFLIGHT_DISK_SPACE'
    }
    $writeProbe = Join-Path $reportRoot '.preflight-write-check'
    New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
    [IO.File]::WriteAllText($writeProbe, 'ok')
    Remove-Item -LiteralPath $writeProbe -Force
    $head = docker exec srbg-intelligence-postgres-1 psql -U srbg -d srbg -At -c 'SELECT version_num FROM alembic_version'
    if ($head.Trim() -ne '0031_controlled_personal_runs') {
        throw "PILOT_PREFLIGHT_MIGRATION_HEAD:$head"
    }
    foreach ($service in @('api','worker','source-discovery')) {
        $environment = docker inspect "srbg-intelligence-$service-1" --format '{{range .Config.Env}}{{println .}}{{end}}'
        if ($environment -notcontains $requiredDiscoverySetting) {
            throw "PILOT_PREFLIGHT_DISCOVERY_ENABLED:$service"
        }
    }
    foreach ($service in @('api','web','worker','scheduler','postgres','redis','minio')) {
        $state = docker inspect "srbg-intelligence-$service-1" --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}'
        $parts = $state.Trim().Split('|')
        if ($parts[0] -ne 'running' -or ($parts[1] -and $parts[1] -ne 'healthy')) {
            throw "PILOT_PREFLIGHT_SERVICE_UNHEALTHY:$service"
        }
    }
    $sourceCount = docker exec srbg-intelligence-postgres-1 psql -U srbg -d srbg -At -c "SELECT count(*) FROM source WHERE base_url IN ('https://www.gov.cn/zhengce/','https://www.mot.gov.cn/','https://xxgk.mot.gov.cn/','https://jtt.sc.gov.cn/','https://www.mem.gov.cn/gk/sgcc/tbzdsgdcbg/')"
    if ($sourceCount.Trim() -ne '5') { throw 'PILOT_PREFLIGHT_SOURCE_SET_INCOMPLETE' }
    $aiEnvironment = docker inspect 'srbg-intelligence-ai-worker-1' --format '{{range .Config.Env}}{{println .}}{{end}}'
    if ($aiEnvironment -contains 'SRBG_AI_PROVIDER=mock') {
        $script:disableAiWorker = $true
    }
}

try {
    Invoke-Preflight
    if ($PreflightOnly) {
        Write-Output 'CONTROLLED_PILOT_PREFLIGHT_OK_NO_NETWORK'
        exit 0
    }
    $powerResult = [SrbgPowerState]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED)
    if ($powerResult -eq 0) { throw 'PILOT_SLEEP_INHIBIT_FAILED' }
    if ($script:disableAiWorker) {
        docker stop srbg-intelligence-ai-worker-1 | Out-Null
    }
    & (Join-Path $PSScriptRoot '..\.tools\uv\uv.exe') run python (Join-Path $PSScriptRoot 'run_controlled_personal_pilot.py') --data-root $DataRoot
    if ($LASTEXITCODE -ne 0) { throw "CONTROLLED_PILOT_FAILED:$LASTEXITCODE" }
}
finally {
    [void][SrbgPowerState]::SetThreadExecutionState($ES_CONTINUOUS)
}
