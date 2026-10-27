# SDR Output Restore Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Direct execution approved.

**Goal:** Retry rejected SDR restoration without changing movie processing.

**Architecture:** Existing DRM request ownership retains explicit SDR intent until
accepted. The native GUI loop drives retries; CB1 stop retains its successor.

**Tech Stack:** Kodi C++20, GBM/DRM atomic, LibreELEC patches, Python unittest.

**Spec:** `docs/superpowers/specs/2026-10-27-sdr-output-restore-design.md`

## Global Constraints

- RC1 branch, build tree, image and installed mini-PCs remain unchanged.
- No publication, film pixel changes or film metadata changes.
- Work in `fix/sdr-output-restore-rc1`; use a sparse source overlay for tests.

## Review Focus

- Property failure and test/real commit rejection must keep restoration pending.
- A successful request must acknowledge the current SDR clear, not an old HDR request.
- A stopped CB1 transaction must retry without a permanent rollback failure.
- A new HDR movie must cancel stale SDR intent; SDR replay must retain it.
- Retry must run even when the GUI is otherwise idle, without a timer or busy loop.

### Task 1: Restore SDR at the accepted atomic boundary

**Files:** Modify the last owning `kodi-9999-zzz-hdr10plus.patch`; add
`tests/cb1/test_sdr_output_restore.py`. Native overlay files are
`WinSystemGbm.cpp`, `WinSystemGbmGLESContext.cpp`, `drm/DRMAtomic.{cpp,h}`.

**Interfaces:** `CDRMAtomic::SetSDRRestorePending(bool)` and
`IsSDRRestorePending() const`, consumed by native output setup/presentation.

- [x] Add a real-method fault-injection test covering property, TEST_ONLY and
  real-commit rejection, retry, repeated stop, HDR/SDR relaunch and idle GUI.
- [x] Run against frozen RC1. Expected: behavioral failures, not compile errors.
- [x] Implement explicit pending intent and acknowledgement only after acceptance.
- [x] Preserve/re-stage the CB1 ordinary successor on stop-only commit rejection.
- [x] Re-run the test. Expected: all scenarios pass.
- [x] Update the existing owning patch, verify it applies and matches overlay.
- [x] Run the complete CB1 suite and compile touched native translation units.
- [x] Verify production diff excludes movie-processing changes and frozen hashes match.
- [ ] Commit locally; perform independent final review; no merge/push/release.
