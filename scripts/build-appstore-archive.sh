#!/usr/bin/env bash
# ==============================================================================
# SriLekh - Apple App Store iOS Archive Build Script (macOS / Xcode CLI)
# Builds the production iOS archive (.ipa) for Apple TestFlight / App Store upload.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/../frontend"
IOS_DIR="$FRONTEND_DIR/ios/App"

echo "=========================================================="
echo "   SriLekh - Building Apple App Store iOS Archive        "
echo "   Architecture: Local-First Offline IndexedDB + Sync    "
echo "=========================================================="

cd "$FRONTEND_DIR"

echo "[1/4] Building Next.js production frontend & offline assets..."
npm run build

echo "[2/4] Syncing web assets & plugins to native iOS platform..."
npx cap sync ios

echo "[3/4] Building iOS Archive using xcodebuild..."
cd "$IOS_DIR"

# Clean build folder
xcodebuild clean -workspace App.xcworkspace -scheme App

# Archive
ARCHIVE_PATH="$IOS_DIR/build/App.xcarchive"
xcodebuild archive \
  -workspace App.xcworkspace \
  -scheme App \
  -configuration Release \
  -archivePath "$ARCHIVE_PATH" \
  CODE_SIGN_STYLE="Automatic"

echo "[4/4] iOS Archive generated successfully!"
echo "Archive Path: $ARCHIVE_PATH"
echo "To upload to TestFlight / App Store:"
echo "1. Run: npx cap open ios (opens in Xcode)"
echo "2. In Xcode: Product -> Archive -> Distribute App -> App Store Connect"
