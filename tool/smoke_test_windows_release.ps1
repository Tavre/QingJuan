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
$previousDisableAdminWeb = $env:QINGJUAN_DISABLE_ADMIN_WEB
$previousAuthTokenDigest = $env:QINGJUAN_AUTH_TOKEN_SHA256
$previousMultiUser = $env:QINGJUAN_MULTI_USER
$previousTwoFactorEncryptionKey = $env:QINGJUAN_2FA_ENCRYPTION_KEY
$env:QINGJUAN_DATA_DIR = Join-Path $smokeRoot "data"
$env:QINGJUAN_TRUST_LOCAL_ADMIN = "1"
$env:QINGJUAN_DISABLE_ADMIN_WEB = "1"
$env:QINGJUAN_AUTH_TOKEN_SHA256 = ""
$env:QINGJUAN_MULTI_USER = "0"
$env:QINGJUAN_2FA_ENCRYPTION_KEY = ""
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
    if ($meta.capabilities.adminWeb) {
        throw "Windows local backend unexpectedly advertises the admin web interface."
    }

    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$Port/admin/" -TimeoutSec 5 -UseBasicParsing | Out-Null
        throw "Windows local backend unexpectedly serves the admin web interface."
    }
    catch {
        $statusCode = [int]$_.Exception.Response.StatusCode
        if ($statusCode -ne 404) {
            throw
        }
    }

    foreach ($hiddenMultiUserPath in @(
        "/api/v1/auth/registration-policy",
        "/api/v1/auth/account/security",
        "/admin/api/registration-settings",
        "/admin/api/users"
    )) {
        try {
            Invoke-WebRequest `
                -Uri "http://127.0.0.1:$Port$hiddenMultiUserPath" `
                -TimeoutSec 5 `
                -UseBasicParsing | Out-Null
            throw "Windows local backend unexpectedly exposes $hiddenMultiUserPath."
        }
        catch {
            $hiddenResponse = $_.Exception.Response
            if ($null -eq $hiddenResponse -or [int]$hiddenResponse.StatusCode -ne 404) {
                throw
            }
        }
    }

    $hiddenMultiUserPosts = @(
        @{ Path = "/api/v1/auth/email-code"; Body = @{ email = "reader@example.com" } },
        @{
            Path = "/api/v1/auth/register"
            Body = @{
                username = "reader"
                email = "reader@example.com"
                password = "release-smoke-password"
            }
        },
        @{
            Path = "/api/v1/auth/login"
            Body = @{ username = "reader"; password = "release-smoke-password" }
        },
        @{
            Path = "/api/v1/auth/login/2fa"
            Body = @{ challengeToken = ("x" * 43); code = "123456" }
        },
        @{
            Path = "/api/v1/auth/github/device/start"
            Body = @{ purpose = "login" }
        },
        @{
            Path = "/api/v1/auth/github/device/poll"
            Body = @{ flowId = ("x" * 43) }
        },
        @{
            Path = "/api/v1/auth/account/github/unbind"
            Body = @{ password = "release-smoke-password" }
        },
        @{
            Path = "/api/v1/auth/account/2fa/setup"
            Body = @{ password = "release-smoke-password" }
        },
        @{
            Path = "/api/v1/auth/account/2fa/enable"
            Body = @{ setupId = ("x" * 43); code = "123456" }
        },
        @{
            Path = "/api/v1/auth/account/2fa/disable"
            Body = @{ password = "release-smoke-password"; code = "123456" }
        },
        @{
            Path = "/api/v1/auth/account/2fa/recovery-codes"
            Body = @{ password = "release-smoke-password"; code = "123456" }
        }
    )
    foreach ($hiddenPost in $hiddenMultiUserPosts) {
        try {
            Invoke-WebRequest `
                -Uri "http://127.0.0.1:$Port$($hiddenPost.Path)" `
                -Method Post `
                -ContentType "application/json" `
                -Body ($hiddenPost.Body | ConvertTo-Json -Compress) `
                -TimeoutSec 5 `
                -UseBasicParsing | Out-Null
            throw "Windows local backend unexpectedly exposes $($hiddenPost.Path)."
        }
        catch {
            $hiddenResponse = $_.Exception.Response
            if ($null -eq $hiddenResponse -or [int]$hiddenResponse.StatusCode -ne 404) {
                throw
            }
        }
    }

    $settings = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/settings" -TimeoutSec 5
    $settings.translationModel.enabled = $false
    $settings.translationModel | Add-Member -NotePropertyName apiKey -NotePropertyValue "" -Force
    $settings.translationModel | Add-Member -NotePropertyName apiKeyAction -NotePropertyValue "keep" -Force
    $settings.mangaOcr | Add-Member -NotePropertyName apiKey -NotePropertyValue "" -Force
    $settings.mangaOcr | Add-Member -NotePropertyName apiKeyAction -NotePropertyValue "keep" -Force
    $settings.bika = @{
        email = ""
        password = ""
        passwordAction = "keep"
    }
    # Windows PowerShell 5.1 otherwise encodes a string request body with the
    # active ANSI code page even when the media type is JSON. Send explicit
    # UTF-8 bytes so settings containing Chinese text round-trip correctly.
    $settingsJson = $settings | ConvertTo-Json -Depth 8 -Compress
    $settingsBody = [System.Text.Encoding]::UTF8.GetBytes($settingsJson)
    $savedSettings = Invoke-RestMethod `
        -Uri "http://127.0.0.1:$Port/api/v1/settings" `
        -Method Put `
        -Headers @{ "X-QingJuan-Local-Request" = "1" } `
        -ContentType "application/json; charset=utf-8" `
        -Body $settingsBody `
        -TimeoutSec 5
    if ($savedSettings.translationModel.enabled) {
        throw "Windows client model settings API did not persist the update."
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
    if ($null -eq $previousDisableAdminWeb) {
        Remove-Item Env:QINGJUAN_DISABLE_ADMIN_WEB -ErrorAction SilentlyContinue
    }
    else {
        $env:QINGJUAN_DISABLE_ADMIN_WEB = $previousDisableAdminWeb
    }
    if ($null -eq $previousAuthTokenDigest) {
        Remove-Item Env:QINGJUAN_AUTH_TOKEN_SHA256 -ErrorAction SilentlyContinue
    }
    else {
        $env:QINGJUAN_AUTH_TOKEN_SHA256 = $previousAuthTokenDigest
    }
    if ($null -eq $previousMultiUser) {
        Remove-Item Env:QINGJUAN_MULTI_USER -ErrorAction SilentlyContinue
    }
    else {
        $env:QINGJUAN_MULTI_USER = $previousMultiUser
    }
    if ($null -eq $previousTwoFactorEncryptionKey) {
        Remove-Item Env:QINGJUAN_2FA_ENCRYPTION_KEY -ErrorAction SilentlyContinue
    }
    else {
        $env:QINGJUAN_2FA_ENCRYPTION_KEY = $previousTwoFactorEncryptionKey
    }
}
