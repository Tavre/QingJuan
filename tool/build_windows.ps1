[CmdletBinding()]
param(
    [switch]$SkipBackend,
    [switch]$AllowFlutterVersionMismatch
)

$ErrorActionPreference = "Stop"
$requiredFlutterVersion = "3.24.3"
$nugetVersion = "6.12.1"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$flutterOutput = Join-Path $projectRoot "build/windows/x64/runner/Release"
$releaseOutput = Join-Path $projectRoot "release/qingjuan-windows"
$backendRoot = Join-Path $projectRoot "python-backend"

function Assert-FlutterVersion {
    $version = flutter --version --machine | ConvertFrom-Json
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
    flutter pub get
    flutter build windows --release

    if (Test-Path -LiteralPath $releaseOutput) {
        Remove-Item -LiteralPath $releaseOutput -Recurse -Force
    }
    New-Item -ItemType Directory -Path $releaseOutput | Out-Null
    Copy-Item -Path (Join-Path $flutterOutput "*") -Destination $releaseOutput -Recurse

    if (-not $SkipBackend) {
        $backendOutput = Join-Path $releaseOutput "backend"
        New-Item -ItemType Directory -Path $backendOutput | Out-Null

        python -m PyInstaller `
            --noconfirm `
            --clean `
            --onefile `
            --name "qingjuan-desktop" `
            --paths $backendRoot `
            --collect-all "curl_cffi" `
            --collect-all "websockets" `
            --collect-all "PIL" `
            --collect-all "pypdfium2" `
            --collect-all "jmcomic" `
            --collect-data "rapidocr" `
            --hidden-import "rapidocr" `
            --hidden-import "rapidocr.inference_engine.onnxruntime" `
            --hidden-import "onnxruntime" `
            --exclude-module "rapidocr.inference_engine.mnn" `
            --exclude-module "rapidocr.inference_engine.openvino" `
            --exclude-module "rapidocr.inference_engine.paddle" `
            --exclude-module "rapidocr.inference_engine.pytorch" `
            --exclude-module "rapidocr.inference_engine.tensorrt" `
            --exclude-module "onnxruntime.quantization" `
            --exclude-module "onnxruntime.tools" `
            --exclude-module "onnxruntime.transformers" `
            --exclude-module "torch" `
            --collect-all "common" `
            --collect-all "Crypto" `
            --hidden-import "yaml" `
            --add-data "$(Join-Path $backendRoot "app/windows_ocr.ps1");app" `
            --add-data "$(Join-Path $projectRoot "pubspec.yaml");." `
            --distpath $backendOutput `
            --workpath (Join-Path $backendRoot "build") `
            --specpath $backendRoot `
            (Join-Path $backendRoot "app/main.py")
    }

    Write-Host "Windows release package created: $releaseOutput"
}
finally {
    Pop-Location
}
