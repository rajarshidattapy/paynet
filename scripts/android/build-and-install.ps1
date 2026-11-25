<#
.SYNOPSIS
  Build the PayNet debug APK in WSL and install it on a USB-connected phone.

.DESCRIPTION
  Buildozer cannot run natively on Windows, so the build runs inside WSL while
  everything is driven from PowerShell:
    1. one-time system setup in WSL (as root, no password needed)
    2. buildozer build inside WSL (first run downloads the Android SDK/NDK,
       several GB, 20-60 minutes; later runs are much faster)
    3. adb install of the newest APK, then launch

  Needs: WSL with a distro, and adb on PATH for the install step.

.PARAMETER Distro      WSL distro name (default: Ubuntu).
.PARAMETER SkipSetup   Skip step 1 once it has succeeded.
.PARAMETER NoInstall   Build only; do not touch the phone.

.EXAMPLE
  .\scripts\android\build-and-install.ps1
  .\scripts\android\build-and-install.ps1 -SkipSetup
#>
param(
    [string]$Distro = 'Ubuntu',
    [switch]$SkipSetup,
    [switch]$NoInstall
)

$ErrorActionPreference = 'Stop'
$PackageId = 'com.paynet.app.sms'   # buildozer package.domain + package.name

function Invoke-Native {
    param([string]$What, [scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

# Repo root -> its WSL path (R:\Paynet -> /mnt/r/Paynet).
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($repo -notmatch '^([A-Za-z]):\\(.*)$') { throw "Unsupported repo path: $repo" }
$wslRepo = '/mnt/' + $Matches[1].ToLower() + '/' + ($Matches[2] -replace '\\', '/')
if ($wslRepo -match '\s') { throw "Repo path must not contain spaces for WSL: $wslRepo" }

if (-not $SkipSetup) {
    Write-Host '== 1/3 WSL setup (apt packages, JDK) ==' -ForegroundColor Cyan
    Invoke-Native 'WSL setup' { wsl -d $Distro -u root -- bash "$wslRepo/scripts/android/setup-wsl.sh" }
}

Write-Host '== 2/3 Build (buildozer, inside WSL) ==' -ForegroundColor Cyan
Write-Host 'First run: accept the Android SDK licenses when asked.'
Invoke-Native 'Build' { wsl -d $Distro -- bash "$wslRepo/scripts/android/build.sh" $wslRepo }

$apk = Get-ChildItem (Join-Path $repo 'app\bin\*.apk') |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $apk) { throw 'Build reported success but no APK was found in app\bin' }
Write-Host "APK: $($apk.FullName)" -ForegroundColor Green

if ($NoInstall) { return }

Write-Host '== 3/3 Install on the phone ==' -ForegroundColor Cyan
if (-not (Get-Command adb -ErrorAction SilentlyContinue)) { throw 'adb not found on PATH' }
$devices = @(adb devices | Select-String '\tdevice$')
if ($devices.Count -ne 1) {
    throw "Expected exactly one authorised device, found $($devices.Count). Run 'adb devices' and unlock the phone / accept the USB-debugging prompt."
}
Write-Host 'Keep the phone unlocked: ColorOS may ask you to confirm the install on screen.'
Invoke-Native 'adb install' { adb install -r $apk.FullName }
Invoke-Native 'launch' { adb shell monkey -p $PackageId -c android.intent.category.LAUNCHER 1 }

Write-Host ''
Write-Host 'Installed and launched. If it crashes, capture the log with:' -ForegroundColor Green
Write-Host '  adb logcat -s python AndroidRuntime'
