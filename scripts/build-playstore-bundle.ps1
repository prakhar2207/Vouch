# ==============================================================================
# SriLekh - Google Play Store AAB Bundle Build Script (Windows PowerShell)
# Builds the production Android App Bundle (.aab) for Google Play Console upload.
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   SriLekh - Building Google Play Android App Bundle     " -ForegroundColor Cyan
Write-Host "   Architecture: Local-First Offline IndexedDB + Sync    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$frontendDir = Join-Path $PSScriptRoot "..\frontend"
Set-Location $frontendDir

Write-Host "`n[1/4] Building Next.js production frontend & offline assets..." -ForegroundColor Yellow
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Next.js frontend build failed." -ForegroundColor Red
    exit 1
}

Write-Host "`n[2/4] Syncing web assets & plugins to native Android platform..." -ForegroundColor Yellow
npx cap sync android
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Capacitor Android sync failed." -ForegroundColor Red
    exit 1
}

Write-Host "`n[3/4] Compiling Android App Bundle (.aab) using Gradle..." -ForegroundColor Yellow
$androidDir = Join-Path $frontendDir "android"
Set-Location $androidDir

if (Test-Path ".\gradlew.bat") {
    .\gradlew.bat bundleRelease
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Notice: Release bundle failed or requires signing. Attempting standard bundle..." -ForegroundColor DarkYellow
        .\gradlew.bat bundle
    }
} else {
    Write-Host "Warning: gradlew.bat not found in $androidDir" -ForegroundColor Red
}

$aabPath = Join-Path $androidDir "app\build\outputs\bundle\release\app-release.aab"
$unsignedAabPath = Join-Path $androidDir "app\build\outputs\bundle\release\app-release-unsigned.aab"

Write-Host "`n[4/4] Verifying generated bundle..." -ForegroundColor Yellow
if (Test-Path $aabPath) {
    Write-Host "`n[SUCCESS] Google Play Android App Bundle ready!" -ForegroundColor Green
    Write-Host "File Path: $aabPath" -ForegroundColor Green
    Write-Host "You can directly upload this file to the Google Play Console (Production / Internal Testing)." -ForegroundColor Cyan
} elseif (Test-Path $unsignedAabPath) {
    Write-Host "`n[SUCCESS] Unsigned Google Play Android App Bundle ready!" -ForegroundColor Green
    Write-Host "File Path: $unsignedAabPath" -ForegroundColor Green
    Write-Host "Sign this file using jarsigner / apksigner or configure your release keystore in android/app/build.gradle." -ForegroundColor Cyan
} else {
    Write-Host "`nTo open the project in Android Studio and build with your visual signing key:" -ForegroundColor Cyan
    Write-Host "Run: npm run cap:open:android (inside frontend directory)" -ForegroundColor Cyan
}

Write-Host "==========================================================" -ForegroundColor Cyan
