# Native output and paused transition implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task, with one fresh final reviewer. No implementation fan-out.

**Goal:** Fix native 1080p DV output and paused HDR10/AI switching on the existing Preview G candidate.

**Architecture:** Correct the proven inconsistency at Kodi's existing window,
DRM or renderer lifecycle owner. Reuse native mode/filter/view authority and
decoded-frame ownership, not a parallel scaler or transport path.

**Tech Stack:** Pinned Kodi GBM/EGL/GLES, existing CB1 adapter, native DRM and current LibreELEC image recipes.

**Spec:** `docs/superpowers/specs/2026-10-27-native-output-pause-design.md`, directly authorized by the user's execution request.

## Global constraints

- Base ec639bec79; preserve the complete image built from226721ab1a as control.
- Master pixels and metadata for matching geometry remain exact; native filter kernels unchanged.
- Kodi alone selects output resolution, whitelist, zoom/aspect and display.
- No forced UHD, kernel validation bypass, frequency forcing, AI/model changes or unrelated optimization.
- Restore settings, probes and owned test media after identity-checked tests on both hosts.
- No GitHub write, publication or changes to other machines.

## Review focus

1. Native 720/1080/UHD outputs, limited GUI size and fractional view geometry must not disagree with scanout dimensions.
2. Same-format and 10-to-8/8-to-10 transitions must retain the right EGL/GBM/DRM owners until accepted or rolled back.
3. Paused mode changes must not depend on future decoded frames or silently unpause.
4. Repeated switches, seek, stop and file replacement must not reuse stale AI source bindings.
5. Non-DV vanilla/fallback, Master fidelity and existing UHD cadence must remain unchanged.

## Task 1: Native 1080p output admission

**Owners:** Existing `WinSystemGbmGLESContext`, `WinSystemGbmEGLContext`, `CDRMAtomic`/`CDRMUtils` and existing native integration tests. Edit only the demonstrated owner.

**Interface:** Existing `SetFullScreen`, `CreateNewWindow`, `SetVideoOutput`, `SetMode` and atomic presentation contracts. No new public selector.

- [x] Capture an exact native 1080p failure with Kodi windowing diagnostics and kernel/plane state; contrast native UHD and vanilla.
- [x] Trace all callers and the unmodified native reference; identify the first inconsistent input before proposing code.
- [x] Add an executable boundary regression test with independently expected geometry/state; observe RED on the base.
- [x] Apply the smallest owner-level fix, observe GREEN, run the full software suite and link Kodi.
- [x] Test native 1080p/UHD Standard, Master and Adaptive on both hosts; preserve view/whitelist and exact Master controls.
- [x] Remove failed trials, stage the existing patch owner and commit the functional fix with evidence.

## Task 2: Paused native HDR10 and AI Reference switching

**Owners:** Existing `RendererVAAPIGLES::CaptureHDR10AIQueue`, `CWinSystemGbmGLESContext::PrepareHDR10AIQueue`/`SetVideoOutput` and their existing lifecycle tests, only where the trace proves the defect.

**Interface:** Existing decoded-picture lease, preparation outcome and surface transaction. Consume Task1's unchanged native output contract.

- [x] Capture the N100 paused native/AI timeout and contrast AMD and unpaused switching.
- [x] Trace source binding, preparation and output commit; add a targeted executable RED test for the missing state transition.
- [x] Fix the existing owner without new queues, model changes or arbitrary delays; observe GREEN and run the full suite.
- [x] Repeat switches in pause and while zoomed, resume/seek/Home/stop and file replacement on both hosts; verify no restart or unexpected fallback.
- [x] Recheck Master exactness and representative UHD cadence, clean unused trials and commit.

## Final qualification

- [x] Fresh source receipts, zero-fuzz patch replay, complete image inspection and native updater delivery to both hosts.
- [x] Re-run both physical reproductions and regression journeys on the exact delivered image.
- [x] One fresh Astra xhigh review of the combined diff; fix demonstrated Important findings by RED/GREEN and full-suite checks.
- [x] Restore both hosts, remove owned temporary artifacts, retain control/final image and record results without publishing.
