[CmdletBinding()]
param(
    [int]$Port = 19453
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$releaseOutput = Join-Path $projectRoot "release/qingjuan-windows"
$versionLine = Get-Content -LiteralPath (Join-Path $projectRoot "pubspec.yaml") -Encoding UTF8 |
    Where-Object { $_ -match "^version:\s*" } |
    Select-Object -First 1
if (-not $versionLine -or $versionLine -notmatch "^version:\s*(\d+\.\d+\.\d+\+\d+)\s*$") {
    throw "pubspec.yaml must contain version: major.minor.patch+build."
}
$expectedVersion = $Matches[1]
$clientPath = Join-Path $releaseOutput "qingjuan.exe"
$flutterLibrary = Join-Path $releaseOutput "flutter_windows.dll"
$flutterAssets = Join-Path $releaseOutput "data/flutter_assets"
$backendPath = Join-Path $releaseOutput "backend/qingjuan-desktop.exe"

foreach ($requiredPath in @($clientPath, $flutterLibrary, $flutterAssets, $backendPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Windows release is missing required client content: $requiredPath"
    }
}

$clientVersion = (Get-Item -LiteralPath $clientPath).VersionInfo
if ($clientVersion.FileVersion -ne $expectedVersion -or
    $clientVersion.ProductVersion -ne $expectedVersion) {
    throw "qingjuan.exe version does not match $expectedVersion."
}

$forbiddenFiles = @(
    Get-ChildItem -LiteralPath $releaseOutput -Recurse -File |
        Where-Object {
            $_.Extension.ToLowerInvariant() -in @(".db", ".sqlite", ".sqlite3", ".pem", ".key")
        }
)
if ($forbiddenFiles.Count -gt 0) {
    throw "Windows release contains runtime data or secret files: $($forbiddenFiles.FullName -join ', ')"
}

$smokeRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "qingjuan-release-smoke-" + [Guid]::NewGuid().ToString("N")
)
New-Item -ItemType Directory -Path $smokeRoot -Force | Out-Null
$previousDataDir = $env:QINGJUAN_DATA_DIR
$previousTrustLocalAdmin = $env:QINGJUAN_TRUST_LOCAL_ADMIN
$previousAuthTokenDigest = $env:QINGJUAN_AUTH_TOKEN_SHA256
$env:QINGJUAN_DATA_DIR = Join-Path $smokeRoot "data"
$env:QINGJUAN_TRUST_LOCAL_ADMIN = "1"
$env:QINGJUAN_AUTH_TOKEN_SHA256 = ""
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
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/healthz" -TimeoutSec 2
            break
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if ($null -eq $health -or $health.status -ne "ok") {
        throw "Packaged backend health check timed out."
    }

    $meta = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/meta" -TimeoutSec 5
    if ($meta.service -ne "qingjuan-backend" -or $meta.appVersion -ne $expectedVersion.Split("+")[0]) {
        throw "Packaged backend metadata does not match the client version."
    }

    $admin = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/admin/" -TimeoutSec 5 -UseBasicParsing
    if ($admin.StatusCode -ne 200) {
        throw "Packaged backend admin assets are unavailable."
    }
    $adminSession = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/admin/api/session" -TimeoutSec 5
    if (-not $adminSession.authenticated -or [string]::IsNullOrWhiteSpace($adminSession.csrfToken)) {
        throw "Packaged backend local admin session is unavailable."
    }

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
        Select-Object -First 1
    $serverProcessId = $listener.OwningProcess
    Write-Output "Windows combined package smoke test passed: version=$expectedVersion"
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
    if ($null -eq $previousDataDir) {
        Remove-Item Env:QINGJUAN_DATA_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:QINGJUAN_DATA_DIR = $previousDataDir
    }
    if ($null -eq $previousTrustLocalAdmin) {
        Remove-Item Env:QINGJUAN_TRUST_LOCAL_ADMIN -ErrorAction SilentlyContinue
    }
    else {
        $env:QINGJUAN_TRUST_LOCAL_ADMIN = $previousTrustLocalAdmin
    }
    if ($null -eq $previousAuthTokenDigest) {
        Remove-Item Env:QINGJUAN_AUTH_TOKEN_SHA256 -ErrorAction SilentlyContinue
    }
    else {
        $env:QINGJUAN_AUTH_TOKEN_SHA256 = $previousAuthTokenDigest
    }
}
