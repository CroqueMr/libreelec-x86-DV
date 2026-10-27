# RC1 Preview2 Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct reproduced Beta5 feedback on the frozen candidate without changing video algorithms.

**Architecture:** Keep output ownership in Kodi's existing windowing owner and GUI composition in the existing compositor. Keep layer assembly in its current demux owner. Do not add a parallel renderer or synthetic recovery data.

**Tech Stack:** Kodi C++/GLES, FFmpeg demux, existing Python actual-source regression tests.

**Spec:** `docs/superpowers/specs/2026-10-27-preview2-feedback-design.md`

## Global Constraints

- Preview1 tag and artifacts remain unchanged; no publication or skin code.
- Master reconstruction, film pixels and source metadata stay unchanged.
- Native filter policy, Adaptive, Bluetooth and display selection stay unchanged.
- No hardware installation or driver changes in this source-correction lot.

## Review Focus

- Ordinary playback after real DV must restore once, then stay native.
- Pending or refused restoration must retain its current owner.
- Mixed PQ subtitles and SDR GUI must not discard or repeatedly blend a layer.
- Mode changes during pause must use current output selection.
- Seek alignment must preserve reference/decode order and not consume the wrong EL.

### Task 1: Restore native ordinary-output ownership

**Files:** `kodi-9999-zz-beta3.patch`, `tests/cb1/test_ordinary_output_isolation.py`, source lock.

- [x] Reproduce actual `SetVideoOutput` and `PrepareDVOutputFrame` with fresh, live-cached and retired contexts.
- [x] Observe RED with ordinary SDR/HDR10/HLG incorrectly taking CB1 ownership.
- [x] Gate transactions on requested output or active DV/HDR-conversion state; guard ordinary staging by actual pending ownership.
- [x] Run targeted isolation/restoration tests: five tests pass.
- [x] Replay integration patches and run the complete suite: owner replay matches; 203 tests pass.

### Task 2: Mixed PGS and GUI in Master

**Files:** Existing windowing owner patch/header and native compositor regression tests.

- [x] Reproduce Beta5 and Preview1 refusing Master preparation for mixed PQ PGS/SDR GUI.
- [x] Prototype a native, generation-idempotent overlay merge and verify alpha/orientation.
- [x] Integrate only after the complete overlay reaches native Master admission.
- [x] Revalidate subtitle-only, GUI-only, repeated pause/menu/mode-change paths, GL-state restoration and next-redraw clearing.

### Task 3: Remaining reported failures

**Files:** Existing demux/pairing owner and lifecycle tests, only after evidence.

- [x] Separate seek, startup, BDMV and MKV/MP4 causes; reproduce a common-IRAP TS seek using real FEL packets. Exact reporter discs/files remain unavailable.
- [x] Add a regression before correcting proven EL-prefix misalignment; retain unknown-clock and malformed-packet guards.
- [x] Inspect HDR-first availability and addon UI residue without speculative resets. Frozen Beta5 and Preview1 recover availability when a new DV codec opens.
- [x] Record unavailable samples and non-reproducing cases as open.

### Task 4: Preview2 qualification and integration handoff

- [x] Run full integration tests (205 pass), native patch replay, actual LibreELEC C++ compilation and source verification.
- [x] Obtain an independent review of the combined changes and address important findings: pending ordinary restoration and merged-GUI cleanliness.
- [x] Set Preview2 source identity; record that images require a subsequent build. CB1 engine identity remains the unchanged frozen revision.
- [x] Provide the bounded owner-patch set and an honest fixed/reproduced/open table; publish nothing. Qualification report remains in the private Preview2 work dossier.

The ordinary-output and mixed-PGS changes share the existing windowing owner;
they remain in that owner patch rather than adding another patch layer.

