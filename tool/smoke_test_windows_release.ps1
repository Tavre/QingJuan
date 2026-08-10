[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ExpectedVersion,
    [int]$Port = 19453
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseOutput = Join-Path $projectRoot "release/qingjuan-windows"
$backendPath = Join-Path $releaseOutput "backend/qingjuan-desktop.exe"
if (-not (Test-Path -LiteralPath $backendPath -PathType Leaf)) {
    throw "Packaged backend was not found: $backendPath"
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "qingjuan-release-smoke-" + [Guid]::NewGuid().ToString("N")
)
New-Item -ItemType Directory -Path $smokeRoot -Force | Out-Null
$env:QINGJUAN_DATA_DIR = Join-Path $smokeRoot "data"
$stdout = Join-Path $smokeRoot "backend.stdout.log"
$stderr = Join-Path $smokeRoot "backend.stderr.log"
$process = Start-Process -FilePath $backendPath -ArgumentList @(
    "serve", "--host", "127.0.0.1", "--port", "$Port", "--parent-pid", "$PID"
) -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr

$serverProcessId = $null
try {
    $health = $null
    for ($attempt = 0; $attempt -lt 100; $attempt++) {
        if ($process.HasExited) {
            $errorOutput = Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue
            throw "Packaged backend exited early: $errorOutput"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
            break
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $health -or $health.status -ne "ok") {
        throw "Packaged backend health check timed out."
    }

    $openapi = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/openapi.json" -TimeoutSec 5
    if ($openapi.info.version -ne $ExpectedVersion) {
        throw "Backend OpenAPI version $($openapi.info.version) does not match $ExpectedVersion."
    }

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $serverProcessId = $listener.OwningProcess
    Write-Output "Packaged backend smoke test passed: status=$($health.status), version=$ExpectedVersion"
}
finally {
    $processIds = @($process.Id)
    if ($null -ne $serverProcessId) {
        $processIds += $serverProcessId
    }
    $processIds += @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { $_.OwningProcess }
    )
    foreach ($processId in ($processIds | Select-Object -Unique)) {
        $ownedProcess = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -eq $ownedProcess) {
            continue
        }
        if ($ownedProcess.Path -ne $backendPath) {
            throw "Refusing to stop unexpected process $processId at $($ownedProcess.Path)."
        }
        Stop-Process -Id $processId -Force
        $ownedProcess.WaitForExit()
    }
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        throw "Packaged backend still owns port $Port after smoke-test cleanup."
    }
}
