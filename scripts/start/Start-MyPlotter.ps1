param(
    [switch]$SkipPull,
    [switch]$SkipRun
)

$ErrorActionPreference = 'Stop'
$RepoUrl = 'https://github.com/oneinflesh/myPlotter.git'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Launcher = Join-Path $RepoRoot 'Start-MyPlotter.cmd'
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$ProjectFile = Join-Path $RepoRoot 'pyproject.toml'
$DependencyStamp = Join-Path $RepoRoot '.venv\myplotter-dependencies.sha256'

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE"
    }
}

try {
    Set-Location -LiteralPath $RepoRoot

    $Desktop = [Environment]::GetFolderPath('DesktopDirectory')
    $ShortcutPath = Join-Path $Desktop 'My Plotter Dev.lnk'
    if (-not (Test-Path -LiteralPath $ShortcutPath)) {
        $Shell = New-Object -ComObject WScript.Shell
        $Shortcut = $Shell.CreateShortcut($ShortcutPath)
        $Shortcut.TargetPath = $Launcher
        $Shortcut.WorkingDirectory = $RepoRoot
        $Shortcut.Description = 'Update and launch My Plotter'
        $Shortcut.Save()
        Write-Host "Created Desktop shortcut: $ShortcutPath"
    }

    if (-not $SkipPull) {
        $Branch = (& git branch --show-current).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $Branch) {
            throw 'Unable to determine the current Git branch.'
        }
        Write-Host "Updating $Branch from $RepoUrl..."
        Invoke-Checked 'git' @('pull', '--ff-only', $RepoUrl, $Branch)
    }

    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Host 'Creating .venv...'
        if (Get-Command py -ErrorAction SilentlyContinue) {
            Invoke-Checked 'py' @('-3', '-m', 'venv', '.venv')
        } else {
            Invoke-Checked 'python' @('-m', 'venv', '.venv')
        }
    }

    $ProjectHash = (Get-FileHash -LiteralPath $ProjectFile -Algorithm SHA256).Hash
    $InstalledHash = if (Test-Path -LiteralPath $DependencyStamp) {
        (Get-Content -LiteralPath $DependencyStamp -Raw).Trim()
    } else { '' }
    & $VenvPython -c "import importlib.util, sys; sys.exit(not all(importlib.util.find_spec(name) for name in ('serial', 'PySide6', 'svgelements', 'myplotter')))"
    $ImportsReady = $LASTEXITCODE -eq 0
    if ($InstalledHash -ne $ProjectHash -or -not $ImportsReady) {
        Write-Host 'Installing project dependencies in .venv...'
        Invoke-Checked $VenvPython @('-m', 'pip', 'install', '--editable', '.')
        Set-Content -LiteralPath $DependencyStamp -Value $ProjectHash
    }

    if (-not $SkipRun) {
        Write-Host 'Starting My Plotter...'
        Invoke-Checked $VenvPython @('-m', 'myplotter.app')
    }
} catch {
    Write-Error $_
    exit 1
}
