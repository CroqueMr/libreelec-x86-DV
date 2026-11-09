# SDR, HLG and Player information Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add integrated HDR/DV SDR rendering, HLG DV Reference and truthful single-line Player information to the current preview.

**Architecture:** Extend existing policy and render contracts, keeping native image reconstruction and one presentation/retirement owner. Kodi selects routes from original source and sink capability, and reports only committed output. The PR92 presentation consumes the existing coherent metadata snapshot.

**Tech Stack:** C, C++, libplacebo, FFmpeg, Kodi XML, Python native-source tests, pinned LibreELEC SDK in WSL DVBuild.

**Spec:** docs/superpowers/specs/2026-11-09-sdr-hlg-player-info.md

## Global Constraints

- No Astra and no Support build.
- Preserve existing numeric IDs; append modes/circuits.
- HLG has ONLY DV Reference and Kodi default, no Adaptive and no HDR conversion.
- SDR profile is independent of the existing HDR profile; BT.709 targets are Reference 100 nits/gamma 2.4 and Bright room 200 nits/gamma 2.2.
- No silent FEL discard or synthetic authored L2/L8; no fallback preference overwrite.
- No grey unused Processing metadata, no wrapped fields, consistent level order.
- Synced sources are read only; preserve current RC4 fixes and main.

## Review Focus

- SDR-only EDID must admit processing without HDR/DV capability.
- HLG-base DV with RPU must retain its DV reconstruction route.
- Rejected presentation, seek and paused switching must never publish stale SDR/DV output.
- Malformed metadata/FEL matching failures must not silently produce a BL-only success.
- Maximum metadata inventories and native Kodi output must remain readable without wrapping or loss.

### Task 1: Engine SDR and HLG contracts

**Files:** CB1/src/dvbridge_policy.{h,c}, cb1_circuit.{h,c}, dvbridge_render.{h,c}; existing AI/analysis owners as required; CB1/tests, CB1/docs.
**Interfaces:** Append DVBRIDGE_MODE_SDR and CB1_DV_SDR / CB1_HDR10_SDR / CB1_HLG_DV_REFERENCE. Add a value-only SDR profile in dvbridge_policy. Expose SDR rendering through the existing prepare/resolve/commit owner; document exact new signatures in the ledger before Kodi uses them. HLG normalization accepts only original HLG, producing the same PQ/BT.2020 domain consumed by the existing AI analysis/rendering.

- [ ] Add behavioral tests for SDR validation/presets, finite custom values, HDR/DV image equivalence after reconstruction, HLG reference normalization, failure identity and output transfer/gamut; run and observe missing-feature failures.
- [ ] Implement minimal contracts and shared renderer reuse, preserving source identity and all-layer DV reconstruction.
- [ ] Run native engine tests (including GPU tests where available), document exact commands/results and commit owned files.

### Task 2: Kodi route integration

**Files:** canonical kodi-9990-cb1-video.patch, kodi-9992-cb1-display.patch, kodi-9993-cb1-interface.patch; tests/cb1 source preference/selection/telemetry tests.
**Interfaces:** Consume Task1 policy and rendering entry points; extend OutputMode/OutputRoute without renumbering old entries. Saved selectors dvbridge.hlgsource and independent SDR profile settings. Telemetry uses actual committed outputhdrtype=sdr and applied source metadata.

- [ ] Add failing native C++ selection tests for DV/HDR SDR on SDR-only sink and HLG-only reference/default, independent saved preferences, fallback retention, invalid profile and 3D/native nonregression.
- [ ] Integrate settings, menu/quick switch, renderer, transport, overlays, source detection and committed telemetry with existing owners.
- [ ] Run focused native tests and matched replay; commit owned files.

### Task 3: Correct PR92 Player information

**Files:** IncludesDVProcessInfo.xml, PR92 textures, a rebased Player information patch, focused tests/cb1 metadata/readability/native snapshot tests; docs/cb1/KODI-INFORMATION.md.
**Interfaces:** Existing VideoProcessingInfo and source snapshot with original/applied/transmitted metadata remain independent. Metadata ordering is numeric by level. Processing hides unapplied blocks. Single-line fields retain long data through scrolling or detail navigation.

- [ ] Add failing tests covering long trim lists, HDR10+, DV FEL/DT, native HDR/HLG/SDR, SDR rendering and pending/fallback states; compare PR source reset/snapshot changes to latest base.
- [ ] Rebase PR92 behavior, remove unused-grey/wrapping and preserve original/source details; keep all columns coherent.
- [ ] Run focused tests and visual validation; commit owned files.

### Task 4: Integration, review and build

**Files:** config/cb1-patch-index.json, config/cb1-source-lock.json and stage receipts; docs/cb1 playback/processing/information/backlog; private proof scripts and build artifacts under work/sdr-hlg-player-info-20261109.
**Interfaces:** Exact combined source identity through source lock, matched replay, tests and image.

- [ ] Refresh authoritative hashes/staging and replay every native patch with fuzz=0 against pinned sources.
- [ ] Run full matched Python/native/engine tests. Review complete diff independently without Astra and resolve material findings with regression tests.
- [ ] Build normal preview; inspect compiled owners, signaling and source provenance, test VM boot/logging and available physical playback/mode transitions.
- [ ] Prepare update artifacts and concise feature changelog/backlog; never claim unperformed physical tests or publish an unqualified build.
