<#
    Builds the Android package and puts it where the app can see it.

    This is the route the spec recommends, because it is the only alt-store path that needs no
    Apple notarisation, no paid developer account and no machine that is not this one: a signed
    .apk served from /store and installed by tapping it.

    What it assumes, stated as plainly as it is true:
      * a JDK 17 and Gradle on this machine. Neither is installed here today, which is exactly why
        data/packages has no .apk in it - the script checks and tells her what to run instead of
        pretending a build happened.
      * signing comes from the four fame* lines scripts/make_keystore.ps1 writes. Without them
        Gradle still compiles, but the output is app-release-unsigned.apk and Android will not
        install it, so this script refuses to publish that as a package.
      * -Debug is the honest shortcut for her own phone: the SDK signs debug builds by itself.

    Usage:
        powershell -ExecutionPolicy Bypass -File scripts\build_apk.ps1
        powershell -ExecutionPolicy Bypass -File scripts\build_apk.ps1 -Debug
#>
param(
    [switch]$Debug
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root 'apk'
$gradleFile = Join-Path $project 'app\build.gradle'
$outDir = Join-Path $project 'app\build\outputs\apk'
$packages = Join-Path $root 'data\packages'

function Resolve-Gradle {
    $wrapper = Join-Path $project 'gradlew.bat'
    if (Test-Path $wrapper) { return $wrapper }
    $onPath = Get-Command gradle -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    return $null
}

$gradle = Resolve-Gradle
if (-not $gradle) {
    Write-Host "No Gradle here, so nothing was built. Three ways to get one, cheapest first:" -ForegroundColor Yellow
    Write-Host "  1. Install Android Studio once, then File > Open this apk folder - it offers to"
    Write-Host "     create apk\gradlew.bat, which is the wrapper this script prefers."
    Write-Host "  2. winget install Gradle.Gradle       (needs a JDK too: EclipseAdoptium.Temurin.17.JDK)"
    Write-Host "  3. Let GitHub Actions build it - .github\workflows\apk.yml, once this repository"
    Write-Host "     has a remote. Download the artifact into data\packages and /store picks it up."
    exit 1
}

if (-not $env:JAVA_HOME -and -not (Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Host "Gradle needs a JDK 17 and this shell has neither JAVA_HOME nor java on PATH." -ForegroundColor Yellow
    Write-Host "  winget install EclipseAdoptium.Temurin.17.JDK"
    exit 1
}

if (-not (Test-Path $gradleFile)) { throw "no build file at $gradleFile" }
$version = [regex]::Match((Get-Content $gradleFile -Raw), "versionName\s+'([^']+)'").Groups[1].Value
if (-not $version) { throw "versionName is not in $gradleFile - the package would be named for nothing" }

$task = if ($Debug) { 'assembleDebug' } else { 'assembleRelease' }
Write-Host "Building $task with $gradle ..."
Push-Location $project
try {
    if ($gradle -like '*gradlew.bat') {
        & $gradle $task
    } else {
        & $gradle -p $project $task
    }
    if ($LASTEXITCODE -ne 0) { throw "Gradle exited $LASTEXITCODE - the APK was not produced." }
} finally {
    Pop-Location
}

$flavour = if ($Debug) { 'debug' } else { 'release' }
$candidates = @(
    (Join-Path $outDir "$flavour\app-$flavour.apk"),
    (Join-Path $outDir "$flavour\app-$flavour-unsigned.apk")
)
$built = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $built) { throw "Gradle reported success but no APK is under $outDir" }

if ($built.Name -like '*-unsigned.apk') {
    Write-Host ""
    Write-Host "Compiled, but the only output was app-release-unsigned.apk - no signing key was" -ForegroundColor Yellow
    Write-Host "found, and Android refuses an unsigned package. Run scripts\make_keystore.ps1 once,"
    Write-Host "or use -Debug for your own phone. Nothing was copied to data\packages."
    exit 1
}

New-Item -ItemType Directory -Force -Path $packages | Out-Null
$suffix = if ($Debug) { '-debug' } else { '' }
$target = Join-Path $packages ("fame-strategist-{0}{1}.apk" -f $version, $suffix)
Copy-Item $built $target -Force
$hash = (Get-FileHash $target -Algorithm SHA256).Hash
$size = [math]::Round((Get-Item $target).Length / 1MB, 1)

Write-Host ""
Write-Host "Published: $target  ($size MB)"
Write-Host "SHA-256:   $hash"
Write-Host "Now open /store on the phone and the table lists it; the download link is the install."
