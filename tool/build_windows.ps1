[CmdletBinding()]
param(
    [switch]$AllowFlutterVersionMismatch
)

$ErrorActionPreference = "Stop"
$requiredFlutterVersion = "3.24.3"
$nugetVersion = "6.12.1"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$flutterOutput = Join-Path $projectRoot "build/windows/x64/runner/Release"
$releaseOutput = Join-Path $projectRoot "release/qingjuan-windows"

function Assert-FlutterVersion {
    $versionOutput = flutter --version --machine
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to query Flutter version; flutter exited with code $LASTEXITCODE."
    }
    $version = $versionOutput | ConvertFrom-Json
    if ($version.frameworkVersion -eq $requiredFlutterVersion) {
        return
    }

    $message = "Flutter $requiredFlutterVersion is required; found $($version.frameworkVersion)."
    if (-not $AllowFlutterVersionMismatch) {
        throw "$message Pass -AllowFlutterVersionMismatch only for migration testing."
    }
    Write-Warning $message
}

function Enable-NuGet {
    if (Get-Command "nuget.exe" -ErrorAction SilentlyContinue) {
        return
    }

    $nugetDirectory = Join-Path $projectRoot ".dart_tool/nuget/$nugetVersion"
    $nugetPath = Join-Path $nugetDirectory "nuget.exe"
    if (-not (Test-Path -LiteralPath $nugetPath)) {
        New-Item -ItemType Directory -Path $nugetDirectory -Force | Out-Null
        $downloadUrl = "https://dist.nuget.org/win-x86-commandline/v$nugetVersion/nuget.exe"
        Write-Host "NuGet was not found. Downloading official version $nugetVersion..."
        Invoke-WebRequest -Uri $downloadUrl -OutFile $nugetPath
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $nugetPath
    $signedByMicrosoft = $signature.SignerCertificate -and
        $signature.SignerCertificate.Subject -match "Microsoft Corporation"
    if ($signature.Status -ne "Valid" -or -not $signedByMicrosoft) {
        Remove-Item -LiteralPath $nugetPath -Force -ErrorAction SilentlyContinue
        throw "NuGet signature validation failed. The downloaded file was removed."
    }

    $env:Path = "$nugetDirectory;$env:Path"
}

Push-Location $projectRoot
try {
    Assert-FlutterVersion
    Enable-NuGet
    flutter config --enable-windows-desktop
    if ($LASTEXITCODE -ne 0) {
        throw "flutter config --enable-windows-desktop failed with exit code $LASTEXITCODE."
    }
    flutter pub get
    if ($LASTEXITCODE -ne 0) {
        throw "flutter pub get failed with exit code $LASTEXITCODE."
    }
    flutter build windows --release
    if ($LASTEXITCODE -ne 0) {
        throw "flutter build windows --release failed with exit code $LASTEXITCODE."
    }

    if (Test-Path -LiteralPath $releaseOutput) {
        Remove-Item -LiteralPath $releaseOutput -Recurse -Force
    }
    New-Item -ItemType Directory -Path $releaseOutput | Out-Null
    Copy-Item -Path (Join-Path $flutterOutput "*") -Destination $releaseOutput -Recurse

    if (Test-Path -LiteralPath (Join-Path $releaseOutput "backend")) {
        throw "Windows remote-client package must not contain a local backend."
    }

    Write-Host "Windows remote-client package created: $releaseOutput"
}
finally {
    Pop-Location
}
