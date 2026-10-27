# Adaptive rev B runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy signed Adaptive rev B alongside current Adaptive on N100.

**Architecture:** Promote the already qualified builder into the engine, gated by an authored-DV policy flag. Reuse Kodi's settings, admission, menu and telemetry.

**Tech Stack:** C/C++, CMake, Kodi/LibreELEC, existing updater and pinned SSH.

**Spec:** docs/superpowers/specs/2026-10-27-adaptive-revb-runtime-design.md

## Global Constraints

- No publication; frozen RC1 V1 and other circuits unchanged.
- N100 only; preserve configuration/media, no TV power-on unless needed.
- Same rev B arithmetic; no image analysis or new shader pass.

## Review Focus

- HDR10 AI must never inherit the rev B flag.
- Switching variants must not blend incompatible history.
- New choice must reuse Adaptive availability, not bypass output capability checks.
- Player information must report the actually accepted variant.
- Image/updater must retain rollback and prove expected source identity.

### Task 1: Runtime integration

**Files:** CB1/src policy/builder/renderer/circuit/CMake; tests; existing owning Kodi patch sections and source receipts.
**Interfaces:** policy.adaptive_rev_b, existing builder API, Kodi output6 -> telemetry8, new circuit identity.

- [x] Add failing runtime dispatch and native preference/label/admission tests.
- [x] Promote builder, route policy, isolate AI/history and expose native Kodi choice.
- [x] Replay owning patches, refresh mechanical digests; run engine and native suites.
- [x] Commit locally and request final independent review; resolve important findings.

### Task 2: Build and deploy

**Files:** existing complete-image build workspace, local qualification receipt and native updater payload.
**Interfaces:** validated source commit -> DV-R1.0.0-RC1-V2.tar -> N100 updater.

- [ ] Build complete image without overwriting V1; inspect version, binary/resources and hashes.
- [ ] Verify N100 identity and snapshot configuration; stage rollback and update through native updater.
- [ ] Verify reboot/version/Kodi, rev B choice, short DV smoke test and stop/return behavior; leave ready for visual tests.
- [ ] Record limitations and receipts; do not publish.
