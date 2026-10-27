# Adaptive rev B signed guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace offline rev B with signed shape and amplitude guidance.

**Architecture:** Test-only builder reuses creative operators and the unchanged renderer. Existing harnesses qualify the replacement.

**Tech Stack:** C, libplacebo, FFmpeg, CMake, Python.

**Spec:** docs/superpowers/specs/2026-10-27-adaptive-rev-b-signed-design.md

## Global Constraints

- Adaptive from authored DV only; no image analysis or runtime changes.
- No mini-PC, TV, publication, additional pipeline or new dependency.
- Keep source immutable, <=10 nits protected and TV ceiling respected.

## Review Focus

- Zero/invalid weights must not silently select a different response.
- Missing primary controls must remain neutral, not decode zero as a trim.
- Opposite signs must survive normalization, including constant gain.
- Extrapolation must reduce authority outside authored target range.
- SDR controls must not leak through a dark-scene temporal transition.

### Task 1: Replace the offline curve builder

**Files:** CB1/tests/prototypes/cb1_dv_adaptive_rev_b.{c,h}, CB1/tests/adaptive_rev_b.c

**Interfaces:** Keep cb1_dv_enhanced_build_rev_b(plan, source, policy) and existing plan ABI.

- [x] Add signed/constant/domain/CM2.9/validation assertions; run adaptive_rev_b and observe the missing behavior fail.
- [x] Replace old builder with the signed guide; run the four adaptive_rev_b tests and full engine suite.
- [x] Commit the tested replacement.

### Task 2: Qualify and review

**Files:** existing GPU harness and summarizer; docs/qualification/2026-10-27-adaptive-rev-b-signed.md and evidence summary.

**Interfaces:** Same renderer substitution and JSON observations as the earlier prototype; separate raw evidence directory.

- [ ] Generate scalar, pixel, film, temporal and three idle GPU timing runs; check effective backend and timing scope.
- [ ] Run native regressions; verify runtime diff from V1 is empty.
- [ ] Document measured gain/cost and limitations; fresh final Astra review, fix important findings with failing tests first.
- [ ] Revalidate, commit locally, leave unpublished.
