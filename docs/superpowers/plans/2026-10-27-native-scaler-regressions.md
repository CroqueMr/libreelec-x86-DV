# Native scaling regression fixes

> **For agentic workers:** Use superpowers:executing-plans inline, one final independent review. No implementer fan-out.

**Goal:** Correct Expert near-black, conversion chroma phase and measured scaled-source performance regressions without modifying Kodi filter algorithms or Master pixels.

**Architecture:** Keep the source-grid/one-native-final-fit boundary. Correct metadata interpretation at its existing owner, propagate source layout through existing adapters, and optimize only work demonstrated redundant or unnecessarily expensive by matched measurements.

**Tech stack:** Existing CB1 C/GLSL, Kodi GLES classes, pinned libplacebo/FFmpeg, current LibreELEC recipe and dual-host observer.

**Spec:** User's 2026-10-27 approval plus `docs/superpowers/specs/2026-10-26-scaling-choice-qualification-design.md`; the prior qualification's DOSSIER-FINAL.md records the demonstrated gaps.

## Global constraints

- Base d3059e908774e728eace5a85eef33ec64fee3707; preserve its image and receipts.
- Original Kodi kernels, Auto/whitelist/view authority and native filtering remain.
- No Master reconstruction, metadata or output-pixel changes, including resized controls.
- No resolution/ratio workaround, second scaler selector, forced clocks, publication or unrelated driver/audio changes.
- Other modes may change where the requested black/chroma corrections require it. Do not mask image errors by changing end-of-chain calibration.
- Keep only measured useful optimizations; clean rejected prototypes and retest.
- Existing N100/AMD3200U test systems only; verify identity and restore settings/files.

## Review focus

1. Near-black absolute PQ samples versus mastering-monitor minimum, with/without creative guidance.
2. LEFT/CENTER/TOPLEFT planar chroma on BL and EL; preserve packed Y416 and native Master phase.
3. Generic crop/zoom/fractional placement and output dimensions; no hardcoded1080p path.
4. Native-fit precision, source leases and pending-frame invalidation across mode/geometry switches.
5. Same-source/segment/view/output/filter benchmarks; unavailable drop counters stay unavailable.

## Task 1: Expert near-black

**Owners:** CB1/src/dvbridge_placebo.c; CB1/tests/expert_black_floor.c; tests/CMakeLists and source receipts.
**Interface:** dvbridge_reference_map and dvbridge_render_hdr10_policy_rgb remain unchanged.

- [ ] Write a GPL-2.0-or-later independent absolute-PQ ramp and L6-minimum witness using existing MIT GPU helpers; demonstrate failure on the base.
- [ ] Prevent the mastering-monitor minimum becoming the Expert content floor, preserving other policies and input metadata.
- [ ] Run the witness and full engine/integration suites; stage the owned source and record RED/GREEN.

## Task 2: Source chroma phase

**Owners:** Existing Kodi RendererVAAPIGLES import/preparation and policy-image owners; existing native integration tests.
**Interface:** Reuse pl_frame_set_chroma_location and existing layout/format guards, not a new sampling algorithm.

- [ ] Trace every source adapter and existing Y416 correction before editing.
- [ ] Reproduce LEFT/CENTER/TOPLEFT behavior on real source-frame imports, including EL where applicable. Derive expected coordinates independently.
- [ ] Correct only missing propagation at the shared owner; test packed/non-subsampled exceptions and unchanged Master behavior.
- [ ] Verify exact native filter kernels/geometry and refresh owning patches/receipts, not an overlay patch.

## Task 3: Scaled-source performance

**Owners:** Existing native-fit and source preparation/packing owners only; private profiler/measurement controls.
**Interface:** Original filter classes, coefficients, selection and Master pixel contract remain unchanged.

- [ ] Profile the native boundary and compare it with the retained control on P5 Standard and Adaptive, with genuine1:1 controls.
- [ ] Test one hypothesis at a time. Remove proven redundant work first; do not assume lower precision or different filtering is the answer.
- [ ] Keep only a qualified useful change. If non-Master storage precision is implicated, quantify output error and preserve Master storage/pixels exactly; no silent global precision downgrade.
- [ ] Recheck generic720/1080/1440/near-UHD geometry and selected native filtering, not merely a named1080p fixture.

## Task 4: Delivery and final review

- [ ] Full engine/integration suites, source/staging, fuzz-free patch replay, Kodi link and complete-image inspection.
- [ ] Install the exact candidate on both identity-checked hosts; matched d305 A/B and prior stabilized-control checks for scaled routes and Master FEL/Gemini.
- [ ] Exercise zoom, mode changes while zoomed, native output/view controls, subtitles, O-cycle, pause/seek/Home/stop. Inspect logs and process/GPU identity.
- [ ] Recheck frozen exact Master witnesses and representative resized native-filter outputs on both GPUs.
- [ ] One independent whole-change review; resolve demonstrated important defects, clean temporary payloads/settings and hand off measured results without publication.
