# Packaging AI RAM Guardian

This package is built for direct macOS distribution first: Developer ID signed, notarized, stapled, and shipped as a DMG.

## Required source files

Before the DMG workflow can succeed, commit the actual product files:

```text
ai-ram-guardian/guardian.mm
ai-ram-guardian/Info.plist
ai-ram-guardian/LaunchAgent.plist
ai-ram-guardian/Makefile
```

The launch-kit files in this branch intentionally do not pretend those sources exist. The workflow fails clearly if `guardian.mm` is missing.

## Local release

```bash
cd ai-ram-guardian
chmod +x scripts/create_dmg.sh
./scripts/create_dmg.sh
```

Output:

```text
dist/AI-RAM-Guardian.dmg
```

## Optional signing

Set:

```bash
export DEVELOPER_ID_APP="Developer ID Application: Your Name (TEAMID)"
```

If the identity exists in the keychain, the script signs the app bundle. If not set, it uses ad-hoc signing so local test builds still work.

## Optional notarization

Set:

```bash
export APPLE_ID="you@example.com"
export APPLE_TEAM_ID="TEAMID"
export APPLE_APP_PASSWORD="app-specific-password"
```

When all three are present, the script submits the DMG with `xcrun notarytool`, waits, and staples the result.

## GitHub Actions release

The workflow `.github/workflows/ai-ram-guardian-dmg.yml` builds on `macos-latest` and uploads a DMG artifact.

For signed CI builds, configure repository secrets:

```text
DEVELOPER_ID_APP
APPLE_ID
APPLE_TEAM_ID
APPLE_APP_PASSWORD
```

A full production CI signing pipeline should also import a Developer ID certificate into the runner keychain. This launch kit leaves that as an explicit buyer/developer step rather than hiding a fake signing process.

## Distribution routes

### Direct paid DMG

Best for the full product because the intervention engine needs process-management capabilities unavailable to a heavily sandboxed store build.

### Mac App Store read-only funnel

Possible product split:

- Read-only ledger viewer.
- Memory/thermal dashboard.
- Share receipt card.
- Education and upgrade funnel.

The MAS build should not claim to background, demote, signal, or manage other processes unless the implementation and entitlements support it.

## Release checklist

- Clean clone builds locally.
- App opens from `/Applications`.
- Menu-bar shield appears.
- Console opens.
- Ledger persists to `~/Library/Application Support/ai-ram-guardian/ledger.jsonl`.
- Log writes to `~/Library/Logs/ai-ram-guardian.log`.
- DMG mounts and app launches after drag-install.
- Gatekeeper allows notarized build.
- Landing page points to the latest release artifact.
- Screenshots are generated and committed.
