$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$env:UV_CACHE_DIR = Join-Path $projectRoot ".cache\uv"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot ".tools\python"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $projectRoot ".cache\ms-playwright"

$toolDirectories = @(
    (Join-Path $projectRoot ".tools\uv"),
    (Join-Path $projectRoot ".tools\node"),
    (Join-Path $projectRoot ".tools\make\tools\install\bin")
)
$env:Path = ($toolDirectories -join ";") + ";" + $env:Path

Write-Output "SRBG local toolchain enabled from $projectRoot"
