# Preview2-C Startup Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, then one independent final review.

**Goal:** Correct reproduced startup/container defects without changing video processing.
**Architecture:** Native FFmpeg/Kodi demux, decoder and navigation owners; existing layer assembler.
**Tech Stack:** C/C++, FFmpeg 9, Kodi 22 RC1, existing Python/C++ regression harnesses.
**Spec:** `docs/superpowers/specs/2026-10-27-preview2-c-startup-design.md`

## Global Constraints

Preview2-A and its archives remain unchanged. No GPU workload optimization,
driver, film-pixel, metadata, filter, Adaptive or skin changes. No publication.
Preserve real packet clocks and relationships; missing evidence is not a fix.

## Review Focus

Parameter-only versus untimestamped picture packets at disc startup.
Separate EL/RPU delivery and access-unit boundaries after seek.
Single-track FEL decoder startup with different container extradata.
Ambiguous MP4 references and ordinary two-camera HEVC files.
HDR-first capability restoration using the actual native caller gate.

### Task 1: Disc startup and BDMV navigation

**Files:** Existing `kodi-9999-bluray-dv.patch` owners CBlurayDovi and
CDVDDemuxFFmpeg::ReadBlurayDovi; native DVDInputStreamBluray only if implicated;
regressions `tests/cb1/test_bluray_pairing.py` and a focused new startup test.
**Interfaces:** Push/Take own packet normalization and pairing, native navigation
chooses title/playlist before demux. Do not conflate these failure boundaries.

- [ ] Re-read #26 log startup sequences and native callers; run baseline suite.
- [ ] Reproduce actual startup packet rejection and BDMV Play path independently.
- [ ] Write failing owner regression preserving non-VCL/VCL and valid/missing clocks.
- [ ] Apply minimum proven owner correction; run test GREEN, replay actual packets
      and full integration suite. Leave non-reproduced navigation cases open.
- [ ] Commit the independently verified correction and record limitations.

### Task 2: MKV FEL decoder startup

**Files:** Existing DVDVideoCodecFFmpeg/FEL integration owners and
`CB1/src/dvbridge_fel.c` only if the failure is demonstrated there; focused test.
**Interfaces:** BL send acceptance, EL submit/device/take and bounded pending BL.

- [ ] Trace the single-track #26 and dual-track #29 paths separately.
- [ ] Replay real local FEL access units in MKV and matched working transport.
- [ ] Add a RED regression only for a demonstrated divergence, fix at the owner,
      run GREEN and non-regressions. No arbitrary timeout/pool increase.
- [ ] Record exact-sample limitations and commit verified changes.

### Task 3: MP4 association and HDR-first availability

**Files:** Existing FFmpeg MOV dependency patch and native Kodi admission owners;
`tests/cb1/test_dual_carriage.py` and existing admission lifecycle tests.
**Interfaces:** Declared FFmpeg stream groups before CBlurayDovi; real codec
initialization before active capability/admission refresh.

- [ ] Compare the report's stream inventory with MOV relationship parsing and
      repeat HDR-first, stop, DV initialization through native methods.
- [ ] Reproduce failures including invalid references, independent tracks and
      failed capability queries. Preserve ordinary HDR behavior.
- [ ] If proved, add RED test, correct owner and run GREEN/full suite; otherwise
      retain explicit open status instead of speculative reset or forced pairing.
- [ ] Commit independently verified changes only.

### Task 4: Qualification and source checkpoint

**Files:** Source receipts, release identity, tests and concise evidence report.
**Interfaces:** Every modified owner must replay exactly from pinned sources.

- [ ] Compile changed owners using the real LibreELEC commands.
- [ ] Run full integration suite and source staging receipts; inspect full result.
- [ ] Obtain independent final review, resolve important findings with tests.
- [ ] Identify Preview2-C, preserve A, clean generated media/build scratch and
      leave the local branch ready without publishing or unsupported fix claims.
