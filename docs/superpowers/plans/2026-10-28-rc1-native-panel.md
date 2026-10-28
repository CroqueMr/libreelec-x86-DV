# RC1 native panel implementation plan

> **For agentic workers:** Use superpowers:executing-plans. Direct execution requested.

**Goal:** Keep only the accepted Adaptive and deliver RC1 with a skin-owned selector.
**Architecture:** CGUIDialogSelect carries items and descriptions; native skin XML owns layout.
**Tech Stack:** Kodi C++, LibreELEC patches, CB1 C, Python regression tests.
**Spec:** docs/superpowers/specs/2026-10-28-rc1-native-panel-design.md

## Constraints and review focus

- No movie shader, reconstruction, source metadata or other circuit changes.
- No publication. Preserve frozen RC1/V2 images and user configuration.
- Expert descriptions, disabled choices and HDR10/DV source lists must fit.
- Ordinary selectors and foreign skins retain their own controls and geometry.
- Saved private rev B preference becomes the retained Adaptive, never Standard.
- Preserve pause/seek and the O cycle; no extra GUI rendering after closing.

## Tasks

1. Native selector regression and fix.
   - [x] Replace the obsolete panel geometry test with upstream-layout and native-item contract checks; observe failure.
   - [x] Remove Estuary selector overrides, geometry code and unused helper.
   - [x] Revalidate native item descriptions, unavailable selection and O handling.
2. Remove rev B and identify RC1.
   - [x] Pin a failing saved-choice migration/removal test.
   - [x] Remove rev B runtime and normalize saved preference 6 to Adaptive 5.
   - [x] Refresh existing patch owners, staging/source receipts and release identifiers.
   - [ ] Run full engine and integration suites and independent final review.
3. Complete image and visual delivery.
   - [ ] Compile and inspect a complete RC1 image, without overwriting frozen artifacts.
   - [ ] Capture the actual native selector with Expert text and movie background.
   - [ ] Restore user settings, remove task-only overrides and report artifact hashes.

## Progress

Scope supplied directly by the user; native layout is selected instead of
adjusting our old constants. Existing linked worktree reused on a separate local
candidate branch. No additional worktree or publication.

Independent review identified an invalid Expert capability probe inherited from
the removed normalization block. Retain the non-Adaptive field reset only;
actual-method regression failed before and passes after. Removed stale selector
entries from the patch catalogue. No remaining review finding deferred.

Engine final: 238 registered, 223 passed, 15 explicit environment skips, zero
failures. Native baseline/removal suite: 211 passed. Final native rerun and image
qualification are separate pending gates.
