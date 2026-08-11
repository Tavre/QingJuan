param(
    [Parameter(Mandatory = $true)]
    [string]$Tag,
    [switch]$ValidateVersionOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pubspecPath = Join-Path $projectRoot "pubspec.yaml"
$versionLine = Get-Content -LiteralPath $pubspecPath -Encoding UTF8 |
    Where-Object { $_ -match '^version:\s*' } |
    Select-Object -First 1
if (-not $versionLine -or
    $versionLine -notmatch '^version:\s*([0-9]+\.[0-9]+\.[0-9]+)\+([0-9]+)\s*$') {
    throw "pubspec.yaml does not contain a valid semantic version and build number."
}

$semanticVersion = $Matches[1]
$normalizedTag = $Tag.TrimStart('v', 'V')
if ($normalizedTag -ne $semanticVersion) {
    throw "Tag $Tag does not match pubspec version $semanticVersion."
}

if ($ValidateVersionOnly) {
    Write-Host "Android release version validated: $semanticVersion"
    exit 0
}

$sourceApk = Join-Path $projectRoot "build/app/outputs/flutter-apk/app-release.apk"
if (-not (Test-Path -LiteralPath $sourceApk)) {
    throw "Release APK was not found: $sourceApk"
}

$releaseDirectory = Join-Path $projectRoot "release/android"
New-Item -ItemType Directory -Force -Path $releaseDirectory | Out-Null
$apkPath = Join-Path $releaseDirectory "QingJuan-v$semanticVersion-android.apk"
$checksumPath = "$apkPath.sha256"
Copy-Item -LiteralPath $sourceApk -Destination $apkPath -Force
$checksum = (Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
"$checksum  $(Split-Path -Leaf $apkPath)" | Set-Content -Encoding ascii $checksumPath

if ($env:GITHUB_OUTPUT) {
    "version=$semanticVersion" | Add-Content -Encoding utf8 $env:GITHUB_OUTPUT
    "apk=$apkPath" | Add-Content -Encoding utf8 $env:GITHUB_OUTPUT
    "checksum=$checksumPath" | Add-Content -Encoding utf8 $env:GITHUB_OUTPUT
}

Write-Host "Android release files created: $apkPath"
