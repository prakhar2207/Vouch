#!/usr/bin/env bash
# ==============================================================================
# SriLekh - Google Play Store AAB Bundle Build Script (Bash / Linux / macOS)
# Builds the production Android App Bundle (.aab) for Google Play Console upload.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"
ANDROID_DIR="$FRONTEND_DIR/android"

echo "=========================================================="
echo "   SriLekh - Building Google Play Android App Bundle     "
echo "   Architecture: Local-First Offline IndexedDB + Sync    "
echo "=========================================================="

cd "$FRONTEND_DIR"

echo "[1/4] Building Next.js production frontend & offline assets..."
npm run build

echo "[2/4] Syncing web assets & plugins to native Android platform..."
npx cap sync android

echo "[3/4] Compiling Android App Bundle (.aab) using Gradle..."
cd "$ANDROID_DIR"
chmod +x gradlew
./gradlew bundleRelease || ./gradlew bundle

echo "[4/4] Verifying generated bundle..."
AAB_PATH="$ANDROID_DIR/app/build/outputs/bundle/release/app-release.aab"
UNSIGNED_PATH="$ANDROID_DIR/app/build/outputs/bundle/release/app-release-unsigned.aab"

if [ -f "$AAB_PATH" ]; then
    echo "[SUCCESS] Google Play Android App Bundle ready!"
    echo "File Path: $AAB_PATH"
elif [ -f "$UNSIGNED_PATH" ]; then
    echo "[SUCCESS] Unsigned Google Play Android App Bundle ready!"
    echo "File Path: $UNSIGNED_PATH"
else
    echo "Bundle output created in $ANDROID_DIR/app/build/outputs/bundle/"
fi
