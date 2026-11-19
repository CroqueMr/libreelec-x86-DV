# Default playback and Player information implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. Steps use checkbox syntax.

**Goal:** Implement the approved defaults, native recovery and panel refinement without changing current information-block positions.

**Architecture:** Reuse existing output-settings mutex/snapshot/revision, native file Prepare boundary, selector, restore/atomic owners and existing skin assets. Amend authoritative existing patches instead of adding another corrective patch layer. No native Kodi optimization, duplicate engine or preference store.

**Tech Stack:** C/C++, Kodi GBM/GLES, existing i915 DV extension if causal, LibreELEC patch ownership, Python actual-body/native tests, matched FFmpeg/libplacebo.

**Spec:** docs/superpowers/specs/2026-11-10-default-playback-and-player-info.md

## Global Constraints

Follow every binding requirement in the spec. Preserve source549 as git baseline and old evidence. Work on isolated branch work/default-playback-panel-20261110. All implementers Sol High, original architecture/quality challenge and final review Astra xhigh. No publication, Support, AMD hardware or PR101/100. Reuse native functions. No moving current panel blocks. No new redundant patch layer.

## Review Focus

- Restore succeeds after a rejected test: old failure must not poison a later native or CB1 file; clear only after acknowledged safe recovery.
- Native 10-bit framebuffer during DV exit must not be classified by stale packet bytes; valid DV8 transport checks must still reject invalid scanout.
- Default and temporary DV method pairs, four source families, unavailable choices, pause/seek, reopen and playlist transitions must retain the correct owner.
- Opaque GUI in HDR10plus/DV/HDR10/SDR, ordinary native rendering, subtitle/capture safety and correct color/range must not depend on a hidden user toggle.
- Same block order/coordinates and property bindings with longest metadata/pending/error values; no scrolling/wrapping/dim-used chips.

### Task 1: Fix owned native restoration and reentry

**Files:** existing Kodi display/atomic owning patches, existing i915 DV helper patch ONLY if proven causal; tests/cb1/test_sdr_output_restore.py and the related actual native atomic/handoff tests. Source targets: WinSystemGbmGLESContext.cpp restore/reject/ack paths; native intel_dv_lab_active only if source tracing proves stale bytes.
**Interfaces:** existing acknowledged restoration/retirement and OutputReason::RestoreFailed; do not add a parallel recovery manager. Exact causal amendment follows the original Astra architecture report before implementation.
- [ ] Reproduce both originating stale-DV/native-format rejection and retained poison with actual source-owner tests; observe RED.
- [ ] Fix shared owners minimally without clearing failed fences/errors blindly; preserve native/DV rejection and real-failure controls.
- [ ] GREEN focused/native compilation and patch replay; commit and original Astra scoped review.

### Task 2: Source defaults, live overrides and coherent native settings

**Files:** existing kodi-9990-cb1-video.patch and kodi-9993-cb1-interface.patch, selection owner if elsewhere, tests/cb1/test_output_menu_recovery.py and focused default-state tests, existing setting/copy checks.
**Interfaces:** DVOutputSettings.h FrameOutputSettings()/OutputSettingsMutex()/SelectOutputSettings(); CVideoPlayer::Prepare() new-file boundary; DVQuickSettings ShowMenu(settingsMenu); DVOutputSelection.h admission. Existing persisted keys remain the default owner; one small session override under existing mutex. Include DV output AND method. No second preference system.
- [ ] Actual-body RED for stored defaults versus live choices, new-file reset, same-session seek/pause, inactive settings display and unavailable circuit rejection.
- [ ] Implement override merge before existing SameValues/revision/decoder atomics; reuse sole production SelectOutputSettings new-file call. Settings write defaults; live menu never saves defaults.
- [ ] Remove two visible technical controls and obsolete override reads; retain safe automatic GUI optimization and authored L5; apply exact approved labels and dependent prefixes.
- [ ] GREEN focused tests/compile/replay; commit and original Astra scoped review.

### Task 3: Rounded opaque panel with existing block placement

**Files:** projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml and existing assets; existing GUI composition owner ONLY if demonstrated by a real pixel regression; tests/cb1/test_process_info_readability.py and existing actual GLES composition checks.
**Interfaces:** existing skin control IDs, FitPanel sizing, all current column/property membership unchanged. Baseline panel-order-baseline.json under work/default-playback-panel-20261110 pins structural requirements. No pagination/extra dialog/new layout engine.
- [ ] Preserve a structural snapshot before changes; add meaningful round-border/opacity/no-wrap and actual composition regression checks where needed.
- [ ] Restore existing PR92 rounded assets/border around the CURRENT arrangement; retain current bright-green/vivid accents and neutral opaque used metadata.
- [ ] Verify HDR10plus-to-DV GUI composition with optimization active, comparing to the correct existing compositing/reference behavior. If no cause is reproduced, report exact coverage rather than inventing one or retuning movie pixels.
- [ ] GREEN focused pixel/UI tests; commit and original Astra review.

### Task 4: Integrate and deliver the local normal preview

**Files:** existing CB1 source/staging/patch locks and package inputs, local task evidence/backlog/notes; new normal local artifact receipts as needed. Do not mutate old source15 evidence.
**Interfaces:** replayed actual source owners, source commit, matched dependency libraries, local normal image and exact installed boot; no new publication adapter.
- [ ] Refresh actual source/dependency/staging locks with existing tools; replay every patch with zero fuzz, compile changed native owners.
- [ ] Run matched full suite once; inspect every failure and legitimate compatibility change, no skips hidden and no test weakened to mirror new code.
- [ ] Build/inspect local normal image if needed for changed runtime/skin verification; no Support/public/OVA distribution. Validate new default/session and native recovery cases, panel geometry and HDR10plus-DV GUI on available N100 with strict ownership/restore and receiver gates.
- [ ] Final original Astra xhigh whole-change correctness/provenance/complexity review; resolve real blockers, keep known hardware limits and no-release policy; local delivery and clean source.
