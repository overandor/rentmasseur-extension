# AI RAM Guardian

Native macOS menu-bar + desktop utility for AI-heavy workflows: Devin, Windsurf, Claude, Cursor, VS Code, and Codex.

The product thesis is simple: memory utilities should not claim magic speedups. They should show receipts.

AI RAM Guardian watches real process memory, real pressure trajectory, real Apple Silicon thermal readings where available, and real intervention outcomes. The strongest feature is the audit ledger: every trim, reclaim, thermal soothe, focus-flow change, and anomaly event is persisted as a receipt.

## Positioning

**The machine steward for AI workstations.**

AI coding tools leak RAM, spawn helpers, keep language servers alive, and heat laptops while the user is switching between apps. Guardian does not pretend to be a generic RAM booster. It is an AI-workstation steward with a glass UI and an auditable savings ledger.

## What is real

- Native macOS app, not Electron, not a web dashboard.
- Menu-bar shield with free memory and chip temperature.
- Glass panel with memory pressure, per-app cards, forecast, receipts, and self-audit.
- Desktop console with measured ledger tiles and receipt timeline.
- FLOW: focus-aware resource easing for non-focused AI helper processes.
- SOOTHE: thermal demote-and-verify receipts.
- RECLAIM: post-trim memory recheck receipts.
- Online Kalman forecast with visible uncertainty.
- Per-app RSS anomaly learning from the user’s own machine.
- Shareable receipt card concept for viral proof.

## What it must never fake

- No fake speed boosts.
- No simulated RAM savings.
- No claimed time savings without labeling assumptions.
- No killing or relaunching whole apps.
- No App Store claim for the full intervention engine unless the sandbox limitations are redesigned around read-only mode.

## Repo structure

```text
ai-ram-guardian/
  guardian.mm                  # native app source; commit your current production file here
  Makefile                     # local build/install target
  Info.plist                   # app metadata
  LaunchAgent.plist            # optional launchd agent
  scripts/create_dmg.sh         # signed/notarized DMG builder
  landing/index.html            # GitHub Pages landing page
  PACKAGING.md                  # release and notarization guide
  PRODUCT.md                    # sale/product narrative
.github/workflows/
  ai-ram-guardian-dmg.yml       # macOS build + DMG artifact workflow
  ai-ram-guardian-pages.yml     # GitHub Pages deployment workflow
```

## Local build

```bash
cd ai-ram-guardian
make app
make install
```

## DMG package

```bash
cd ai-ram-guardian
./scripts/create_dmg.sh
```

The script builds `AI RAM Guardian.app`, signs it when a Developer ID identity is available, optionally notarizes when Apple credentials are supplied, and outputs a compressed DMG.

## Distribution plan

Full intervention engine: direct Developer ID + notarized DMG.

App Store-compatible funnel: read-only Ledger edition, share cards, onboarding, and education. The App Store edition should not claim it can manage other processes unless the implementation fits sandbox rules.

## Sale framing

Raw code is a prototype. The product is the measured ledger: a machine-health app where every claim has a receipt.
