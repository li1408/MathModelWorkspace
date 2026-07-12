param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Continue"
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$LocalDir = Join-Path $ProjectRoot ".local"
$LocalBin = Join-Path $LocalDir "bin"
$LocalTemp = Join-Path $LocalDir "temp"
$MiktexPathFile = Join-Path $LocalDir "miktex-bin.path"
$PerlPathFile = Join-Path $LocalDir "perl-bin.path"

function Read-PathFile {
    param([string]$Path)
    if (Test-Path $Path) {
        return ((Get-Content -Path $Path -TotalCount 1) -join "").Trim()
    }
    return ""
}

$MiktexBin = Read-PathFile $MiktexPathFile
$PerlBin = Read-PathFile $PerlPathFile

New-Item -ItemType Directory -Force -Path $LocalTemp | Out-Null
$env:TEMP = $LocalTemp
$env:TMP = $LocalTemp

$pathParts = @()
if (Test-Path $LocalBin) { $pathParts += $LocalBin }
if ($PerlBin -and (Test-Path $PerlBin)) { $pathParts += $PerlBin }
if ($MiktexBin -and (Test-Path $MiktexBin)) { $pathParts += $MiktexBin }
$pathParts += $env:PATH
$env:PATH = ($pathParts -join ";")

function Write-Check {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Message
    )
    Write-Output "[$Status] $Name - $Message"
}

function Run-Capture {
    param(
        [string]$Command,
        [string[]]$Arguments = @()
    )
    $output = & $Command @Arguments 2>&1
    return @{
        ExitCode = $LASTEXITCODE
        Output = $output
    }
}

$hasError = $false

Write-Output "CUMCM2026 LaTeX environment check"
Write-Output "ProjectRoot: $ProjectRoot"
Write-Output "Local wrapper bin: $LocalBin"
Write-Output "MiKTeX bin: $MiktexBin"
Write-Output "Perl bin: $PerlBin"
Write-Output "Temp dir: $LocalTemp"

$perlWhere = Run-Capture "where.exe" @("perl")
if ($perlWhere.ExitCode -eq 0) {
    Write-Check "where.exe perl" "OK" (($perlWhere.Output | Select-Object -First 1) -join "")
    $perlVersion = Run-Capture "perl" @("-v")
    if ($perlVersion.ExitCode -eq 0) {
        Write-Check "perl -v" "OK" (($perlVersion.Output | Select-Object -First 2) -join " ")
    } else {
        $hasError = $true
        Write-Check "perl -v" "ERROR" "Perl was found, but perl -v failed."
    }
} else {
    $hasError = $true
    Write-Check "where.exe perl" "ERROR" "Perl is not available in PATH."
    Write-Output "FIX: Install Perl for Windows, preferably outside C: for this workspace, then rerun scripts\setup_local_paths.ps1."
    Write-Output "NOTE: latexmk depends on Perl. This is an environment problem, not a LaTeX source-code error."
}

$latexmkWhere = Run-Capture "where.exe" @("latexmk")
if ($latexmkWhere.ExitCode -eq 0) {
    Write-Check "where.exe latexmk" "OK" (($latexmkWhere.Output | Select-Object -First 1) -join "")
    $latexmkVersion = Run-Capture "latexmk" @("-v")
    if ($latexmkVersion.ExitCode -eq 0) {
        Write-Check "latexmk -v" "OK" (($latexmkVersion.Output | Select-Object -First 4) -join " ")
    } else {
        $hasError = $true
        $message = ($latexmkVersion.Output | Select-Object -First 4) -join " "
        Write-Check "latexmk -v" "ERROR" $message
        if ($message -match "Perl") {
            Write-Output "FIX: latexmk was found, but it cannot run because Perl is missing."
            Write-Output "NOTE: Do not treat this as a LaTeX source-code error."
        }
    }
} else {
    $hasError = $true
    Write-Check "where.exe latexmk" "ERROR" "latexmk is not available in PATH."
}

$initexmf = Run-Capture "initexmf" @("--report")
if ($initexmf.ExitCode -eq 0) {
    $config = ($initexmf.Output | Where-Object { $_ -match "^Configuration:" } | Select-Object -First 1)
    $userInstall = ($initexmf.Output | Where-Object { $_ -match "^UserInstall:" } | Select-Object -First 1)
    Write-Check "initexmf --report" "OK" (($config, $userInstall) -join " ")
    if ($config -notmatch "Portable") {
        Write-Check "MiKTeX configuration" "WARNING" "MiKTeX is not running in portable mode. Check .local path wrappers before compiling."
    }
} else {
    $hasError = $true
    Write-Check "initexmf --report" "ERROR" (($initexmf.Output | Select-Object -First 4) -join " ")
}

$ctex = Run-Capture "kpsewhich" @("ctexart.cls")
if ($ctex.ExitCode -eq 0 -and $ctex.Output) {
    Write-Check "kpsewhich ctexart.cls" "OK" (($ctex.Output | Select-Object -First 1) -join "")
} else {
    $hasError = $true
    Write-Check "kpsewhich ctexart.cls" "ERROR" "Missing MiKTeX package: ctex."
}

$bst = Run-Capture "kpsewhich" @("gbt7714-numerical.bst")
if ($bst.ExitCode -eq 0 -and $bst.Output) {
    Write-Check "kpsewhich gbt7714-numerical.bst" "OK" (($bst.Output | Select-Object -First 1) -join "")
} else {
    $hasError = $true
    Write-Check "kpsewhich gbt7714-numerical.bst" "ERROR" "Missing MiKTeX package: gbt7714."
}

$sty = Run-Capture "kpsewhich" @("gbt7714.sty")
if ($sty.ExitCode -eq 0 -and $sty.Output) {
    Write-Check "kpsewhich gbt7714.sty" "OK" (($sty.Output | Select-Object -First 1) -join "")
} else {
    $hasError = $true
    Write-Check "kpsewhich gbt7714.sty" "ERROR" "Missing MiKTeX package: gbt7714."
}

if ($hasError) {
    Write-Output "Environment check finished with blockers."
    exit 1
}

Write-Output "Environment check passed."
exit 0
