[CmdletBinding()]
param()

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

foreach ($requiredPath in @($clientPath, $flutterLibrary, $flutterAssets)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Windows release is missing required client content: $requiredPath"
    }
}

$clientVersion = (Get-Item -LiteralPath $clientPath).VersionInfo
if ($clientVersion.FileVersion -ne $expectedVersion -or
    $clientVersion.ProductVersion -ne $expectedVersion) {
    throw "qingjuan.exe version does not match $expectedVersion."
}

$forbiddenBackend = Join-Path $releaseOutput "backend"
if (Test-Path -LiteralPath $forbiddenBackend) {
    throw "Windows release contains a forbidden local backend: $forbiddenBackend"
}

$forbiddenFiles = @(
    Get-ChildItem -LiteralPath $releaseOutput -Recurse -File |
        Where-Object {
            $_.Name -match "(?i)python|qingjuan-desktop" -or
            $_.Extension.ToLowerInvariant() -in @(".db", ".sqlite", ".sqlite3", ".pem", ".key")
        }
)
if ($forbiddenFiles.Count -gt 0) {
    throw "Windows release contains local-backend, runtime, data, or secret files: $($forbiddenFiles.FullName -join ', ')"
}

Write-Output "Windows remote-client package smoke test passed: version=$expectedVersion"
