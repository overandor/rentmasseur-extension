#!/usr/bin/env bash
set -euo pipefail

APP_NAME="AI RAM Guardian"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
CONTENTS="$APP_BUNDLE/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
DMG_PATH="$DIST_DIR/AI-RAM-Guardian.dmg"
TMP_DMG="$DIST_DIR/AI-RAM-Guardian.tmp.dmg"
VOLUME_NAME="AI RAM Guardian"

cd "$ROOT_DIR"

if [[ ! -f guardian.mm ]]; then
  echo "error: ai-ram-guardian/guardian.mm is missing. Commit the production source before packaging." >&2
  exit 2
fi

mkdir -p "$MACOS" "$RESOURCES" "$DIST_DIR"
rm -rf "$APP_BUNDLE" "$TMP_DMG" "$DMG_PATH"
mkdir -p "$MACOS" "$RESOURCES"

if [[ -f Info.plist ]]; then
  cp Info.plist "$CONTENTS/Info.plist"
else
  cat > "$CONTENTS/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>guardian</string>
  <key>CFBundleIdentifier</key><string>com.overandor.airamguardian</string>
  <key>CFBundleName</key><string>AI RAM Guardian</string>
  <key>CFBundleDisplayName</key><string>AI RAM Guardian</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
fi

clang++ -std=gnu++17 -O2 -Wall -Wextra -fobjc-arc \
  -framework Cocoa -framework QuartzCore -framework IOKit \
  guardian.mm -o "$MACOS/guardian"

chmod +x "$MACOS/guardian"

SIGN_IDENTITY="${DEVELOPER_ID_APP:-}"
if [[ -n "$SIGN_IDENTITY" ]]; then
  echo "Signing with: $SIGN_IDENTITY"
  codesign --force --deep --options runtime --timestamp --sign "$SIGN_IDENTITY" "$APP_BUNDLE"
else
  echo "No DEVELOPER_ID_APP set; using ad-hoc signature for local testing."
  codesign --force --deep --sign - "$APP_BUNDLE"
fi

STAGING="$BUILD_DIR/dmg-staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp -R "$APP_BUNDLE" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

hdiutil create \
  -volname "$VOLUME_NAME" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDRW \
  "$TMP_DMG" >/dev/null

hdiutil convert "$TMP_DMG" -format UDZO -imagekey zlib-level=9 -o "$DMG_PATH" >/dev/null
rm -f "$TMP_DMG"

if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
  echo "Submitting DMG for notarization..."
  xcrun notarytool submit "$DMG_PATH" \
    --apple-id "$APPLE_ID" \
    --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --wait
  xcrun stapler staple "$DMG_PATH"
else
  echo "Skipping notarization: APPLE_ID, APPLE_TEAM_ID, or APPLE_APP_PASSWORD not set."
fi

shasum -a 256 "$DMG_PATH" | tee "$DMG_PATH.sha256"

echo "Created: $DMG_PATH"
