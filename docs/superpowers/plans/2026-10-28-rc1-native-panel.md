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
   - [x] Run full engine and integration suites and independent final review.
3. Complete image and visual delivery.
   - [ ] Compile and inspect a complete RC1 image, without overwriting frozen artifacts.
   - [ ] Capture the actual native selector with Expert text and movie background.
   - [ ] Restore user settings, remove task-only overrides and report artifact hashes.

## Progress

Additional task requested during compilation: Expert-level Disable L2 trims,
default false, only Standard/Master authored DV. Native settings and frame
revision capture are implemented inline; the isolated engine helper/test was
delegated in parallel with disjoint file ownership. No shared writer/serializer
change. A new review covers this addition; a new complete image supersedes the
pre-L2 output, which is not installed or published.

New gate: verify CRC-valid L2-only output removal, unchanged source/all movie
pixels, explicit exclusion of Adaptive/AI/HDR paths, live on/off revisions and
default-false Expert schema. Engine and native full suites must be rerun before
the final complete image and actual screenshot.

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

L2 engine gate: 239 registered, 224 passed, 15 explicit environment skips,
zero failures. Independent final L2 review found stale transmitted-block
telemetry; commit-time capture and L2-only telemetry filtering were added.
The producer regression failed before the fix and passes after it, including
source-block preservation and off/on/off restoration. Review then reported no
remaining finding. A native full rerun under the build account failed solely
on read access to the matched libplacebo fixture; the final rerun uses the
fixture owner's access, without altering production sources or test coverage.

Final native suite: 212 passed, zero failures (196.616 seconds). Complete engine
and source/staging verification are green. The full L2 image and N100 visual
checks remain the final delivery gates.
