param(
    [string]$VhdPath = 'D:\SRBGData\srbg-data.vhdx',
    [string]$DataRoot = '/mnt/host/wsl/SRBGDataDisk/srv'
)

$ErrorActionPreference = 'Stop'
$expectedRoot = [IO.Path]::GetFullPath('D:\SRBGData')
$resolvedVhd = [IO.Path]::GetFullPath($VhdPath)
$mountName = 'SRBGDataDisk'
$mountBase = '/mnt/host/wsl/SRBGDataDisk'
$mountRoot = $DataRoot.TrimEnd('/')
$sysnativeWsl = Join-Path $env:SystemRoot 'Sysnative\wsl.exe'
$system32Wsl = Join-Path $env:SystemRoot 'System32\wsl.exe'
$wsl = if (Test-Path -LiteralPath $sysnativeWsl) { $sysnativeWsl } else { $system32Wsl }

try {
    if (-not $resolvedVhd.StartsWith($expectedRoot + [IO.Path]::DirectorySeparatorChar)) {
        throw 'VHD path is outside D:\SRBGData'
    }
    if (-not (Test-Path -LiteralPath $resolvedVhd -PathType Leaf)) {
        throw "VHD does not exist: $resolvedVhd"
    }
    if ($mountRoot -notmatch '^/mnt/host/wsl/SRBGDataDisk(?:/[A-Za-z0-9._-]+)*/srv$') {
        throw 'PERSONAL_DATA_ROOT_REJECTED'
    }

    # wsl.exe --mount --vhd is invoked through the absolute system path below.
    $ErrorActionPreference = 'Continue'
    & $wsl -d docker-desktop -- sh -lc "test -d '$mountBase'" 2>$null
    $mountedExitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($mountedExitCode -ne 0) {
        $ErrorActionPreference = 'Continue'
        & $wsl --mount --vhd $resolvedVhd --name $mountName 2>$null
        $mountExitCode = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($mountExitCode -ne 0) {
            throw 'wsl.exe --mount --vhd failed'
        }
    }

    $ErrorActionPreference = 'Continue'
    & $wsl -d docker-desktop -- sh -lc (
        "test -d '$mountRoot/postgres' && " +
        "test -d '$mountRoot/postgres-wal' && " +
        "test -d '$mountRoot/minio' && " +
        "test -d '$mountRoot/anchor-minio' && " +
        "test -d '$mountRoot/redis' && " +
        "test -d '$mountRoot/prometheus' && " +
        "test -d '$mountRoot/grafana'"
    ) 2>$null
    $verifyExitCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($verifyExitCode -ne 0) {
        throw 'mounted VHD is missing required service directories'
    }
    & $wsl -d docker-desktop -u root -- sh -lc (
        "chown 65534:65534 '$mountRoot/prometheus' && " +
        "chown 472:0 '$mountRoot/grafana' && " +
        "chmod 0750 '$mountRoot/prometheus' '$mountRoot/grafana'"
    )
    if ($LASTEXITCODE -ne 0) {
        throw 'observability data permissions could not be restored'
    }
    Write-Output "Personal data root ready: $mountRoot"
}
catch {
    Write-Error "PERSONAL_DATA_MOUNT_FAILED: $($_.Exception.Message)"
    exit 1
}
