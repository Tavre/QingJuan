# 青卷 Windows OCR 调用脚本：通过 WinRT 公开 API（Windows.Media.Ocr）识别图片文字与坐标。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File windows_ocr.ps1 -ImagePath <png> [-Languages "ja,zh-Hans,en"]
# 输出：单行 JSON { ok, engineLang, width, height, lines:[{ text, bbox:[x1,y1,x2,y2] }] }
param(
    [Parameter(Mandatory = $true)][string]$ImagePath,
    [string]$Languages = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Emit-Error([string]$message) {
    $obj = [ordered]@{ ok = $false; error = $message }
    Write-Output ($obj | ConvertTo-Json -Compress -Depth 6)
    exit 0
}

try {
    # 加载 WinRT 类型投影。
    [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
    [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
    [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
    Add-Type -AssemblyName System.Runtime.WindowsRuntime

    # WinRT 异步操作 → 同步等待的辅助方法。
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
            $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
        })[0]

    function Await($op, $resultType) {
        $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($op))
        $task.Wait(-1) | Out-Null
        $task.Result
    }

    if (-not (Test-Path -LiteralPath $ImagePath)) {
        Emit-Error "image not found: $ImagePath"
    }

    $absolutePath = (Resolve-Path -LiteralPath $ImagePath).Path
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($absolutePath)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

    # 按优先语言创建引擎，失败则回退到用户配置语言或首个可用语言。
    $engine = $null
    $engineLang = ""
    $candidates = @()
    if ($Languages) { $candidates = $Languages.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ } }
    foreach ($tag in $candidates) {
        try {
            $lang = New-Object Windows.Globalization.Language($tag)
            if ([Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($lang)) {
                $candidate = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
                if ($candidate) { $engine = $candidate; $engineLang = $tag; break }
            }
        }
        catch {}
    }
    if (-not $engine) {
        $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
        if ($engine) { $engineLang = $engine.RecognizerLanguage.LanguageTag }
    }
    if (-not $engine) {
        $avail = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
        if ($avail.Count -gt 0) {
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($avail[0])
            if ($engine) { $engineLang = $avail[0].LanguageTag }
        }
    }
    if (-not $engine) {
        Emit-Error "no OCR engine available; install a Windows language OCR pack"
    }

    $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

    $lines = @()
    foreach ($line in $result.Lines) {
        $minX = [double]::PositiveInfinity; $minY = [double]::PositiveInfinity
        $maxX = [double]::NegativeInfinity; $maxY = [double]::NegativeInfinity
        foreach ($word in $line.Words) {
            $r = $word.BoundingRect
            if ($r.X -lt $minX) { $minX = $r.X }
            if ($r.Y -lt $minY) { $minY = $r.Y }
            if (($r.X + $r.Width) -gt $maxX) { $maxX = $r.X + $r.Width }
            if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
        }
        if ($maxX -le $minX -or $maxY -le $minY) { continue }
        $lines += [ordered]@{
            text = $line.Text
            bbox = @([int][math]::Floor($minX), [int][math]::Floor($minY), [int][math]::Ceiling($maxX), [int][math]::Ceiling($maxY))
        }
    }

    $payload = [ordered]@{
        ok         = $true
        engineLang = $engineLang
        width      = [int]$bitmap.PixelWidth
        height     = [int]$bitmap.PixelHeight
        lines      = $lines
    }
    Write-Output ($payload | ConvertTo-Json -Compress -Depth 6)
}
catch {
    Emit-Error $_.Exception.Message
}
