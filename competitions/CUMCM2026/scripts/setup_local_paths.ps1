$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$localDir = Join-Path $projectRoot ".local"
$localBin = Join-Path $localDir "bin"
$localTemp = Join-Path $localDir "temp"
$pipCache = Join-Path $localDir "pip-cache"
$matplotlibConfig = Join-Path $localDir "matplotlib"
$jupyterConfig = Join-Path $localDir "jupyter\config"
$jupyterData = Join-Path $localDir "jupyter\data"
$jupyterRuntime = Join-Path $localDir "jupyter\runtime"
$miktexPathFile = Join-Path $localDir "miktex-bin.path"
$perlPathFile = Join-Path $localDir "perl-bin.path"
$legacyMiktexJunction = Join-Path $localDir "miktex-bin"
$legacyPerlJunction = Join-Path $localDir "perl-bin"

New-Item -ItemType Directory -Force -Path $localDir | Out-Null
New-Item -ItemType Directory -Force -Path $localBin | Out-Null
New-Item -ItemType Directory -Force -Path $localTemp | Out-Null
foreach ($path in @($pipCache, $matplotlibConfig, $jupyterConfig, $jupyterData, $jupyterRuntime)) {
    New-Item -ItemType Directory -Force -Path $path | Out-Null
}

function Remove-LegacyLocalLink {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return
    }

    $resolvedRoot = (Resolve-Path $localDir).Path
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.FullName -notlike "$resolvedRoot*") {
        throw "Refusing to remove a path outside .local: $($item.FullName)"
    }
    if ($item.LinkType -ne "Junction" -and $item.LinkType -ne "SymbolicLink") {
        throw "Path exists and is not a link managed by this script: $Path"
    }

    try {
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
    } catch {
        if ($item.PSIsContainer) {
            [System.IO.Directory]::Delete($item.FullName, $false)
        } else {
            [System.IO.File]::Delete($item.FullName)
        }
    }
    Write-Output "Removed legacy link: $Path"
}

function Find-MiktexBin {
    $candidates = @(
        "E:\Tools\MiKTeXPortable-CUMCM\app\texmfs\install\miktex\bin\x64",
        "E:\Tools\MiKTeX-25.12-clean\Programs\miktex\bin\x64",
        "E:\Tools\MiKTeX\Programs\miktex\bin\x64"
    )

    $pathCommand = Get-Command xelatex -ErrorAction SilentlyContinue
    if ($pathCommand) {
        $candidates += (Split-Path -Parent $pathCommand.Source)
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path (Join-Path $candidate "xelatex.exe"))) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

function Find-PerlBin {
    $candidates = @(
        "E:\Tools\Strawberry\perl\bin"
    )

    $pathCommand = Get-Command perl -ErrorAction SilentlyContinue
    if ($pathCommand) {
        $candidates += (Split-Path -Parent $pathCommand.Source)
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path (Join-Path $candidate "perl.exe"))) {
            return (Resolve-Path $candidate).Path
        }
    }

    return $null
}

function Write-ToolWrapper {
    param(
        [string]$Name,
        [string]$ExecutablePath,
        [string]$MiktexBin,
        [string]$PerlBin
    )

    if (-not (Test-Path $ExecutablePath)) {
        Write-Warning "Cannot create wrapper for $Name because the executable is missing: $ExecutablePath"
        return
    }

    $wrapperPath = Join-Path $localBin "$Name.cmd"
    $lines = @(
        "@echo off",
        "setlocal",
        "set ""MIKTEX_BIN=$MiktexBin""",
        "set ""PERL_BIN=$PerlBin""",
        "set ""TEMP=$localTemp""",
        "set ""TMP=$localTemp""",
        "if not ""%PERL_BIN%""=="""" (set ""PATH=%MIKTEX_BIN%;%PERL_BIN%;%PATH%"") else (set ""PATH=%MIKTEX_BIN%;%PATH%"")",
        """$ExecutablePath"" %*",
        "exit /b %ERRORLEVEL%"
    )
    Set-Content -Path $wrapperPath -Value $lines -Encoding ASCII
    Write-Output "Created wrapper: $wrapperPath -> $ExecutablePath"
}

$miktexBin = Find-MiktexBin
if (-not $miktexBin) {
    throw "Could not locate xelatex.exe. Install MiKTeX or add MiKTeX to PATH."
}

$perlBin = Find-PerlBin
if (-not $perlBin) {
    Write-Warning "Could not locate perl.exe. latexmk will not run until Perl is installed."
    $perlBin = ""
}

# MiKTeX portable must be launched through its real path. A junctioned bin path
# can make MiKTeX fall back to another regular installation.
Remove-LegacyLocalLink -Path $legacyMiktexJunction
Remove-LegacyLocalLink -Path $legacyPerlJunction

Set-Content -Path $miktexPathFile -Value $miktexBin -Encoding ASCII
Set-Content -Path $perlPathFile -Value $perlBin -Encoding ASCII
Write-Output "Recorded MiKTeX bin: $miktexBin"
Write-Output "Recorded Perl bin: $perlBin"

$tools = @("xelatex", "bibtex", "kpsewhich", "miktex", "initexmf", "mpm", "latexmk")
foreach ($tool in $tools) {
    Write-ToolWrapper `
        -Name $tool `
        -ExecutablePath (Join-Path $miktexBin "$tool.exe") `
        -MiktexBin $miktexBin `
        -PerlBin $perlBin
}
