# v1.0: Windows初回セットアップ。APIキー・有料生成には触れません。
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
function Refresh-ToolPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + $env:Path
    $ffPackageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Packages'
    if (Test-Path -LiteralPath $ffPackageRoot) {
        Get-ChildItem -LiteralPath $ffPackageRoot -Directory -Filter 'Gyan.FFmpeg*' | ForEach-Object {
            Get-ChildItem -LiteralPath $_.FullName -Filter ffmpeg.exe -File -Recurse | ForEach-Object { $env:Path = $_.DirectoryName + ';' + $env:Path }
        }
    }
}
function Find-Python311 {
    $pythonCandidate = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python311/python.exe'
    if (Test-Path -LiteralPath $pythonCandidate) { return $pythonCandidate }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $pythonCandidate = & py -3.11 -c 'import sys;print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $pythonCandidate)) { return $pythonCandidate }
        } catch { $pythonCandidate = $null }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            $pythonCandidate = & python -c 'import sys;print(sys.executable if sys.version_info[:2]==(3,11) else "")' 2>$null
            if ($pythonCandidate -and (Test-Path -LiteralPath $pythonCandidate)) { return $pythonCandidate }
        } catch { $pythonCandidate = $null }
    }
    return $null
}
Refresh-ToolPath
$kitPython = Find-Python311
if ($CheckOnly) {
    if (-not $kitPython) { throw 'Python 3.11 is missing. Run 01_setup.bat.' }
    foreach ($tool in @('ffmpeg','ffprobe')) { if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is missing. Run 01_setup.bat." } }
    Write-Output '[OK] Python 3.11, FFmpeg and FFprobe found. No installation or API calls.'
    exit 0
}
if (-not $kitPython) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install App Installer from Microsoft Store, then retry. See the guide.' }
    Write-Output '[SETUP] Installing Python 3.11. Please review installer prompts.'
    & winget install --id Python.Python.3.11 --exact --source winget --scope user
    if ($LASTEXITCODE -ne 0) { throw 'Python installation did not finish.' }
    Refresh-ToolPath
    $kitPython = Find-Python311
    if (-not $kitPython) { throw 'Close this window and run 01_setup.bat again.' }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Install App Installer from Microsoft Store, then retry.' }
    Write-Output '[SETUP] Installing FFmpeg. Please review installer prompts.'
    & winget install --id Gyan.FFmpeg --exact --source winget
    if ($LASTEXITCODE -ne 0) { throw 'FFmpeg installation did not finish.' }
    Refresh-ToolPath
}
$venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $kitPython -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local Python environment.' }
}
& $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed. Check the internet connection and retry.' }
& $venvPython (Join-Path $PSScriptRoot 'engine/run.py') doctor
if ($LASTEXITCODE -ne 0) { throw 'Environment check failed.' }
& $venvPython (Join-Path $PSScriptRoot 'engine/media.py') check
if ($LASTEXITCODE -ne 0) { throw 'Video download / transcription tools are missing. Check the internet connection and retry.' }
& $venvPython (Join-Path $PSScriptRoot 'engine/media.py') prepare
if ($LASTEXITCODE -ne 0) { Write-Output '[NOTE] Transcription data is not downloaded yet. The packing recipe still works. Run 01_setup.bat again on a good connection.' }
Write-Output '[OK] Setup complete. Open 02_start.bat.'
