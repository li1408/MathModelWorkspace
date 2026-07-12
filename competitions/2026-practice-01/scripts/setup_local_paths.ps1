$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$localDir = Join-Path $projectRoot ".local"
$junction = Join-Path $localDir "miktex-bin"

New-Item -ItemType Directory -Force -Path $localDir | Out-Null

$miktexBin = $null
$pathCommand = Get-Command xelatex -ErrorAction SilentlyContinue
if ($pathCommand) {
    $miktexBin = Split-Path -Parent $pathCommand.Source
}

if (-not $miktexBin) {
    $coreKey = "HKCU:\Software\MiKTeX.org\MiKTeX\2.9\Core"
    if (Test-Path $coreKey) {
        $userRoots = (Get-ItemProperty -Path $coreKey).UserRoots
        if ($userRoots) {
            $candidate = Join-Path $userRoots "miktex\bin"
            if (Test-Path (Join-Path $candidate "xelatex.exe")) {
                $miktexBin = $candidate
            }
        }
    }
}

if (-not $miktexBin) {
    throw "Could not locate xelatex.exe. Install MiKTeX or add MiKTeX to PATH."
}

if (Test-Path $junction) {
    $item = Get-Item $junction
    if ($item.LinkType -eq "Junction") {
        cmd /c rmdir "$junction"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to remove existing junction: $junction"
        }
    } else {
        throw "Path exists and is not a junction: $junction"
    }
}

New-Item -ItemType Junction -Path $junction -Target $miktexBin | Out-Null
Write-Output "Created $junction -> $miktexBin"
