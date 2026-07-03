# Local Mac Metal CI/CD

AI RAM Guardian can use GitHub Actions as a remote control plane while keeping native builds, hardware telemetry, and future Metal/ML training local to the Mac.

## Core idea

```text
GitHub workflow_dispatch
  -> your self-hosted Apple Silicon runner
  -> compile native guardian.mm
  -> package DMG locally
  -> write hardware telemetry receipt
  -> upload only safe build artifacts and receipts
```

This is not cloud training and not fake CI. The Mac does the work. GitHub only triggers, logs, and stores selected artifacts.

## Why this matters

GitHub-hosted macOS runners are useful for clean builds, but they are not your local machine. They cannot observe your real Devin/Windsurf/Claude workload, your actual thermal behavior, or your machine-specific Metal profile.

A self-hosted runner turns your Mac into the CI machine. That allows a new product loop:

```text
local workload -> measured receipt -> build artifact -> model/training update -> next release
```

## What the workflow does

The workflow is:

```text
.github/workflows/ai-ram-guardian-local-mac-metal.yml
```

It runs only on a runner labeled:

```text
self-hosted, macOS, ARM64, metal
```

It performs:

1. Checkout.
2. Verify Apple Silicon ARM64.
3. Verify `ai-ram-guardian/guardian.mm` exists.
4. Collect a local Metal/hardware telemetry receipt.
5. Build the DMG locally with `scripts/create_dmg.sh`.
6. Upload safe artifacts: hardware summary, receipts, DMG, sha256.

## Privacy rule

The workflow must only collect hardware/build telemetry:

- machine model
- OS version
- memory size
- GPU/Metal capability summary
- build artifact hash
- Guardian receipts intentionally emitted by the app

It must not collect:

- user documents
- prompts
- chats
- private app content
- secrets
- browser data
- unrelated process dumps

## Setup: self-hosted runner labels

On the Mac runner, register it with labels:

```text
self-hosted
macOS
ARM64
metal
```

The workflow will not run on a generic runner. That is deliberate.

## Future ML/Metal training loop

The safe product path is not collecting private user content. The valuable dataset is machine behavior:

```text
timestamp
available memory
memory pressure slope
thermal state
average chip temperature
eligible helper RSS
intervention type
before/after delta
build version
hardware profile hash
```

This supports local models such as:

- on-device anomaly thresholds
- per-machine memory pressure forecasting
- policy tuning for when not to trim
- thermal response prediction
- release regression detection

## Real ML, not theater

The correct models for this product are small, inspectable, and local:

- Online Kalman filters for pressure trajectory.
- Exponentially weighted per-app baselines.
- Tiny logistic or decision-tree policies for intervention eligibility.
- Optional MLX/Metal local training for per-machine policy tuning.

A heavy transformer in a RAM guardian is usually wrong. The model must cost less than the waste it prevents.

## Webpage URL

When Pages is enabled for this repo and the Pages workflow runs, the landing page URL should be:

```text
https://overandor.github.io/rentmasseur-extension/
```

If this package is moved to a dedicated repository, the future URL should be:

```text
https://overandor.github.io/ai-ram-guardian/
```

## Current limitation

The launch kit is staged inside `rentmasseur-extension` because a separate connected `ai-ram-guardian` repository was not available through the connector. The correct final product structure is a dedicated repo.
