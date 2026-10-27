# Adaptive rev B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution, then one independent Astra review. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Qualify a separate, metadata-guided Adaptive rev B offline circuit without changing the current candidate's active circuits.

**Architecture:** Add one explicit authored-DV plan builder beside the existing builder, reusing its plan and shader. The offline GPU qualification substitutes only that builder and uses the real render/metadata path. No runtime UI or image change.

**Tech Stack:** C, existing CB1/libplacebo/FFmpeg, CMake/CTest, Python standard library, local EGL.

**Spec:** `docs/superpowers/specs/2026-10-27-adaptive-rev-b-design.md`.

## Global Constraints

- No mini-PC, TV, remote hardware or publication.
- Existing paths and AI model unchanged; no new GPU pass or metadata correction.
- Source freeze is distinct from the previously compiled RC1 image.
- Master/non-prototype pixels and metadata unchanged.
- Title ends in `rev B`.

## Review Focus

- L1/L3 editorial scope versus measured frame statistics: report residual error, never label it Dolby analysis.
- SDR secondary trims must not control HDR expansion or mutate transmitted trims.
- Curves must remain monotone and preserve dark pixels for targets below/above mastering peak.
- Temporal state must not leak between baseline and rev B; resets and unchanged pause must be deterministic.
- GPU cost and rendering backends must be explicit; no N100/AMD-mini-PC extrapolation.

## Task 1: Freeze and characterize baseline

- [x] Record clean HEAD and create V1 checkpoint/V2 branch.
- [x] Configure an isolated offline test build using existing matched dependencies.
- [x] Run existing Adaptive, metadata, policy, AI and Master checks; record baseline failures/unsupported checks.

## Task 2: Separate rev B plan

**Files:** `CB1/tests/prototypes/cb1_dv_adaptive_rev_b.c`, `.h`, `CB1/tests/adaptive_rev_b.c`, `CB1/tests/CMakeLists.txt`. Runtime engine sources remain unchanged.

**Interface:** `cb1_dv_enhanced_build_rev_b(plan, source, policy)` reuses the existing plan type and status contract, accepting only the current authored Adaptive precision policies. Existing public builders retain their semantics.

- [x] Write and run failing behavioral checks for separate rev B, selectivity, SDR-secondary exclusion, HDR trim sensitivity, source immutability and black/peak bounds.
- [x] Implement the smallest separate builder; no shared-shader changes.
- [x] Verify green, including temporal slew and separate histories.

## Task 3: Offline qualification and challenge

**Files:** `CB1/tests/adaptive_rev_b_gpu.c`, one result summarizer under `CB1/tests/reference/`, `docs/qualification/2026-10-27-adaptive-rev-b.md`.

- [x] Exercise actual shader and output metadata with the builder substituted only in the qualification binary.
- [x] Compare pixels, output metadata, protected blacks, color ratios, temporal sequences and original block preservation.
- [x] Measure CPU plan time and available GPU elapsed time after warmup, paired/interleaved baseline/rev B. Identify backend and timer limitations.
- [x] Run full offline engine suite and available native integration suite; identify unsupported checks.
- [x] Prove source diff scope and unchanged baseline shader/build image.
- [ ] Give Astra the spec, diff and measured report; resolve important issues with tests and retain any limits explicitly.

## Execution record

User approved direct prototype execution with final Astra challenge. No further implementation approval gate is needed for this bounded prototype.
