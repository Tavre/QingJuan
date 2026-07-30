[CmdletBinding()]
param(
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$flutterOutput = Join-Path $projectRoot "build/windows/x64/runner/Release"
$releaseOutput = Join-Path $projectRoot "release/qingjuan-windows"
$backendRoot = Join-Path $projectRoot "python-backend"

Push-Location $projectRoot
try {
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
            --collect-all "jmcomic" `
            --collect-all "common" `
            --collect-all "Crypto" `
            --hidden-import "yaml" `
            --add-data "$(Join-Path $backendRoot "app/windows_ocr.ps1");app" `
            --distpath $backendOutput `
            --workpath (Join-Path $backendRoot "build") `
            --specpath $backendRoot `
            (Join-Path $backendRoot "app/main.py")
    }

    Write-Host "Windows 发布包已生成：$releaseOutput"
}
finally {
    Pop-Location
}
