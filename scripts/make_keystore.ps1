<#
    One-time: the signing key an APK needs before Android will install it.

    A debug build is signed by the SDK automatically, so this is only for a release build - the
    one that can be handed to another phone and kept. keytool ships with any JDK 17, and if
    Android Studio is installed its own runtime has it too, so the script looks in both places
    before it asks her to install anything.

    The passwords never land in the repository. They are appended to %USERPROFILE%\.gradle\
    gradle.properties, which is Gradle's own user-level config: outside the project, read by every
    build from this machine, and invisible to git. app/build.gradle looks up the same four names
    with findProperty, so this file is the only place a secret lives.

    Usage:
        powershell -ExecutionPolicy Bypass -File scripts\make_keystore.ps1
        powershell -ExecutionPolicy Bypass -File scripts\make_keystore.ps1 -Alias fame -ValidDays 10000
#>
param(
    [string]$Alias = 'fame',
    [int]$ValidDays = 10000,
    [string]$CommonName = 'Fame Strategist'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$keyDir = Join-Path $root 'keystore'
$store = Join-Path $keyDir 'fame.keystore'

function Find-Keytool {
    $onPath = Get-Command keytool -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $candidates = @(
        "$env:ProgramFiles\Android\Android Studio\jbr\bin\keytool.exe",
        "$env:LOCALAPPDATA\Programs\Android Studio\jbr\bin\keytool.exe",
        "$env:ProgramFiles\Java\*\bin\keytool.exe"
    )
    foreach ($pattern in $candidates) {
        $hit = Get-Item $pattern -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

$keytool = Find-Keytool
if (-not $keytool) {
    Write-Host "No keytool found, so no key was made. Any of these gives you one:" -ForegroundColor Yellow
    Write-Host "  winget install EclipseAdoptium.Temurin.17.JDK"
    Write-Host "  or open Android Studio once - its bundled runtime has keytool in jbr\bin"
    exit 1
}

if (Test-Path $store) {
    Write-Host "A key already exists at $store" -ForegroundColor Yellow
    Write-Host "Keeping it: re-using this file is what lets an update install over the old app."
    Write-Host "Delete it yourself only if you mean to start a brand-new signing identity."
    exit 0
}

New-Item -ItemType Directory -Force -Path $keyDir | Out-Null

Write-Host "Two questions, both asked here and both kept on this machine."
$storeSecure = Read-Host 'Keystore password' -AsSecureString
$keySecure = Read-Host 'Key password (Enter to make it the same)' -AsSecureString
if ($keySecure.Length -eq 0) { $keySecure = $storeSecure }

$plain = [Runtime.InteropServices.Marshal]::PtrToStringUni(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($storeSecure))
$keyPlain = [Runtime.InteropServices.Marshal]::PtrToStringUni(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($keySecure))

& $keytool -genkeypair -v -keystore $store -alias $Alias -keyalg RSA -keysize 2048 `
    -validity $ValidDays -storepass $plain -keypass $keyPlain `
    -dname "CN=$CommonName, OU=self-hosted, O=self-hosted, C=US"
if ($LASTEXITCODE -ne 0) { throw "keytool exited $LASTEXITCODE - the key was not created." }

$gradleHome = Join-Path $env:USERPROFILE '.gradle'
New-Item -ItemType Directory -Force -Path $gradleHome | Out-Null
$props = Join-Path $gradleHome 'gradle.properties'
$lines = @(
    "fameKeystore=$($store -replace '\\', '/')",
    "fameKeystorePassword=$plain",
    "fameKeyAlias=$Alias",
    "fameKeyPassword=$keyPlain"
)
$existing = @()
if (Test-Path $props) {
    $existing = Get-Content $props | Where-Object { $_ -notmatch '^\s*fame' }
}
Set-Content -Path $props -Value ($existing + $lines) -Encoding utf8

Write-Host ""
Write-Host "Signed releases will use $store, and the four fame* lines in $props."
Write-Host "That file holds the passwords in plain text on this machine only - not in git,"
Write-Host "not in this repository, and not anywhere a phone can read."
