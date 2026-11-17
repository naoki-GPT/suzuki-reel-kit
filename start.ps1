# v1.0: キット内の環境で操作画面を開く。共有PCの他案件は参照しない。
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + $env:Path
$ffPackageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Packages'
if (Test-Path -LiteralPath $ffPackageRoot) {
    Get-ChildItem -LiteralPath $ffPackageRoot -Directory -Filter 'Gyan.FFmpeg*' | ForEach-Object {
        Get-ChildItem -LiteralPath $_.FullName -Filter ffmpeg.exe -File -Recurse | ForEach-Object { $env:Path = $_.DirectoryName + ';' + $env:Path }
    }
}
$venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run 01_setup.bat first. See the guide.' }
& $venvPython (Join-Path $PSScriptRoot 'engine/app.py')
if ($LASTEXITCODE -ne 0) { throw 'The app stopped. See the message above.' }
