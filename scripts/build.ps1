param([switch]$IncludeMediaTools)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create the project .venv first; see README.md.' }
Push-Location $root
try {
    & $python -m PyInstaller --noconfirm --clean --windowed --onedir --name VideoDownloader --distpath (Join-Path $root 'dist') --workpath (Join-Path $root 'build') (Join-Path $root 'main.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    $destination = Join-Path $root 'dist\VideoDownloader'
    $toolDir = Join-Path $destination 'tools'
    New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
    $core = Join-Path $env:LOCALAPPDATA 'VideoDownloader\tools\yt-dlp.exe'
    if (-not (Test-Path -LiteralPath $core)) { $core = Join-Path $root 'tools\yt-dlp.exe' }
    if (-not (Test-Path -LiteralPath $core)) { throw 'Install the verified download core first.' }
    Copy-Item -LiteralPath $core -Destination $toolDir -Force
    if ($IncludeMediaTools) {
        foreach ($name in @('ffmpeg.exe', 'ffprobe.exe', 'node.exe')) {
            $cmd = Get-Command $name -ErrorAction Stop
            $file = Get-Item -LiteralPath $cmd.Source
            if ($file.Target) { $source = @($file.Target)[0] } else { $source = $file.FullName }
            Copy-Item -LiteralPath $source -Destination (Join-Path $toolDir $name) -Force
        }
    }
    foreach ($name in @('README.md', 'THIRD_PARTY_NOTICES.md')) {
        Copy-Item -LiteralPath (Join-Path $root $name) -Destination $destination -Force
    }
    if (Test-Path -LiteralPath (Join-Path $root 'licenses')) {
        Copy-Item -LiteralPath (Join-Path $root 'licenses') -Destination $destination -Recurse -Force
    }
    Write-Output "Built: $destination\VideoDownloader.exe"
} finally {
    Pop-Location
}