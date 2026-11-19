# RC1 Preview G: Kodi-owned output scaling implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task by task, followed by an independent final review. Steps use checkbox syntax for tracking.

**Goal:** Remove CB1's competing UHD output selection and redundant spatial routing, while keeping native Kodi output behavior, reference fidelity and measured performance.

**Architecture:** Kodi owns mode selection, rectangles and filter preference; CB1 owns source-grid processing, metadata and transport. Reuse native spatial shader/kernel code before packing, with a real 1:1 bypass. Select the minimum interop implementation from a measured native adapter trial; do not add an unconditional frame-sized copy merely to call a native function.

**Execution clarification:** use the actual native Kodi scaler, with its existing
filter lifecycle and kernels. No lighter substitute or rewritten fused scaling
shader. Preserve current unscaled/identity optimizations, but do not call a
custom interpolation implementation native. Measure necessary native passes
honestly rather than concealing their cost with a different filter.

**Tech Stack:** Existing C/C++/GLES shaders, pinned Kodi22RC1/libplacebo/FFmpeg, current CB1 lease/identity APIs, existing WSL cross build and Intel/AMD test harness.

**Spec:** `docs/superpowers/specs/2026-10-26-kodi-native-scaling-design.md`.
**Cases:** `docs/superpowers/specs/2026-10-26-kodi-native-scaling-cases.md`.

## Global Constraints

- Baseline source `832d970cc7`; preserved branch `checkpoint/rc1-preview-f-before-native-kodi-scaler-20261026`.
- Work branch `candidate/rc1-preview-g-kodi-native-scaling`; build `DV-R1.0.0-RC1-PreviewG`, future tag `R1.0.0-RC1-PreviewG`.
- Installed PreviewE images remain unchanged during framing; a manifest change is not a compiled/installed PreviewG image.
- No publication, driver/kernel, demux/audio, AI-model/creative-curve changes, new quality tier, queue or forced clock.
- Native Auto, whitelist, adjustment Off, overrides and per-video preferences retain native semantics. No second CB1 upscale preference.
- Master: exact reconstruction/metadata before final scaling and exact unchanged no-resample output. Resized output follows the same unmodified Kodi filter as other modes, per explicit user clarification; no Master-only final scaler.
- Native spatial sampling never receives already packed Dolby bytes. P5 retains its component domain.
- FEL reconstruction scaling remains independent. Native/fallback and MVC/stereo routes remain native.
- One route is finished, simplified and requalified before opening the next. Remove failed production trials before another candidate.
- Pending target/context is not Unsupported; no fake 4K allocation, persistent negative-capability cache or stale scanout.
- Do not claim arbitrary DV timing compatibility from an EDID/whitelist entry or a headless scaler test.
- Rollout gate: keep the existing production mode-selection behavior through Tasks1-6. Exercise new targets in isolated qualification probes/builds only. Remove the global CB1 UHD override atomically in Task7 after every reachable CB1 route has qualified target-aware fitting, packing and admission. No permanent per-route selection flag or new fallback policy.

## Review Focus

1. Cold startup can select a new mode after source probing; retain DV identity and do not permanently gray its modes because the old drawable is not admitted.
2. Visible crop, allocation padding, anamorphic pixels and GUI logical dimensions can all differ; infer neither source nor physical target from one width field.
3. Native output shaders can clamp, dither or change range/precision; spatial reuse must not reapply color/tone mapping or damage P5/Master.
4. Pending async work can outlive a filter/mode/target change; no mixed generation, recycled import or duplicated final fit.
5. Replacing a fused scale/pack with an extra FP32 pass can erase the performance win; qualify complete accepted HDMI playback after cleanup, not only a shader timer.

## Owning files and patch discipline

- Kodi paths below are native source paths in the existing owning patch sections, principally `projects/Generic/patches/kodi/kodi-9999-zz-beta3.patch`. Regenerate those sections through the existing checked `native-edit.py` workflow, not an overlay patch on top.
- Native: `xbmc/windowing/Resolution.cpp`; `xbmc/cores/VideoPlayer/VideoRenderers/{RenderManager.cpp,LinuxRendererGLES.cpp/.h,DVBridgeGLES.cpp/.h}`; `.../VideoShaders/{VideoFilterShaderGLES.cpp/.h,ConvolutionKernels.cpp}`; `xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp`.
- Engine: `CB1/src/{dvbridge_render.c/.h,dvbridge_gl_pack.c/.h,pack_gles300.frag,cb1_transport_glsl.h}` and their existing tests/receipts.
- Existing tests: `tests/cb1/test_dv_uhd_mode.py`, `test_fel_upscaling.py`, `test_output_menu_recovery.py`, `test_async_output_admission.py`, `test_output_window_teardown.py`; `CB1/tests/{resolution_contract.c,frame_geometry.c,gles_pack.c,metadata_transport.c,overlay_metadata.c,profile5_images.c,master_reference.c,reference_scaled_output.c,hdr10_ai_transport.c}`.
- New regression owners only where existing ones cannot express the native boundary: `tests/cb1/test_native_output_selection.py` (replace the obsolete force-UHD test, do not retain both contracts), `tests/cb1/test_native_spatial_contract.py`.
- Update `config/cb1-source-lock.json`, `CB1/config/owned-sources.json` and staged mirrors with existing tools after real changes. No new dependency or vendored Kodi filter implementation in CB1.

## Task 1: Freeze baseline and qualify the real native adapter boundary

**Files:** Existing private native-scaler witness, then the native filter/renderer test owner; design's Boundary contract if a measured decision resolves it.
**Consumes:** Current source-sized processed textures, actual original Kodi shader/kernel implementations and the accepted native-ownership design.
**Produces:** A measured adoption choice and a pinned minimal handoff: borrowed processed `pl_frame`/texture with real representation/precision/crop, current identity/lease, native source/destination rectangles and actual output target. Existing `pl_frame`/`pl_tex` and renderer ownership remain the types; no generic render graph.

- [ ] Pin the same-source/output baseline for all current routes, including Master/P5 complete carrier and metadata controls. Record the known pre-existing alternate AMD witness separately.
- [ ] Turn the private whitelist reproducer into the new native-output-selection test: R01 must fail on current code. Retain current vanilla results as the oracle, not obsolete force-UHD assertions.
- [ ] Exercise actual native filter lifecycle and state restoration, not merely hand-compiled shader source: G01/G07/G13/G16, F01/F04/F08, T07, L02/L10.
- [ ] Compare direct native spatial reuse plus final pack with current fused bilinear/packed output. Measure the extra target writes, allocations and synchronization as well as time. No temporary target is forced on a 1:1/fused path.
- [ ] Pin the exact interop call sites and signatures before Task2. Prefer existing `CDVBridgeGLES::{GetPQTexture,Pack,Presented,CaptureSubmission}` and CB1 accessors where their domain/lifetime contract is sufficient. If a processed-frame view is needed, add one borrowed accessor rather than a second processing engine; preserve existing picture/target identity assertions.
- [ ] Decision gate: adopt only if component domain/precision/lifetime are explicit and native spatial reuse does not introduce an unqualified pass or Master difference. If both direct reuse and an existing fusion opportunity fail this gate, record the measured blocker and return the interface decision; do not silently ship an LP filter labeled native.
- [ ] Remove failed private adapter variants after recording compact evidence. Update later Interfaces blocks to the pinned API before their implementation; no later task may guess this handoff.

Expected: source-based native selection RED reproduced; chosen adapter controls pass on both GPUs with explicit fidelity results. This gate does not itself qualify new DV HDMI targets.

## Task 2: Generalize the final target and transport coherently

**Files:** `dvbridge_render.c/.h`, `dvbridge_gl_pack.c/.h`, `pack_gles300.frag`, `cb1_transport_glsl.h`; `gles_pack.c`, `frame_geometry.c`, `metadata_transport.c`, `overlay_metadata.c`, `resolution_contract.c`.
**Consumes:** Task1's pinned handoff and actual target dimensions; existing `dvbridge_gl_pack(...width,height...)` and prepared-picture identities.
**Produces:** Final target, raster stride, packet/parity coverage, flip and overlays derived from the validated target, preserving the frozen UHD transport exactly. Do not widen physical driver capability claims.

- [ ] Add target-size witnesses for 1920x1080, 2560x1440 and UHD; include metadata row crossing, last covered pixel, flip, invalid capacity/alignment and physical/logical-grid mismatch (T01-T07, G18).
- [ ] Run them before changes. Expected RED: current fixed-UHD pack/admission rejects a valid test target; unchanged UHD exact controls still pass.
- [ ] Parameterize only target-dependent stride, flip, viewport, masks and packet indexing in the existing owners. Keep source dimensions, chroma phase, metadata bits and reference constants distinct.
- [ ] Reuse current metadata serialization and GL state isolation; validate arithmetic and packet capacity before any submission. No second packing implementation or per-resolution shader file.
- [ ] Run exact UHD controls and new target/reference-oracle controls. Expected: exact payload/parity/coverage, correct empty/border regions and explicit invalid-target rejection.
- [ ] Clean duplicated fixed-target branches only after all their transport consumers have moved; repeat the same controls and update receipts.

## Task 3: Standard native fitting, including P5; selection remains gated

**Files:** Owning `Resolution`, `RenderManager`, `LinuxRendererGLES`, `DVBridgeGLES` and GBM sections; `dvbridge_render.c/.h`; native selection/spatial tests, `profile5_images.c`, `resolution_contract.c`.
**Consumes:** Task1 handoff and Task2 target-aware transport. Native `ChooseBestResolution`, `UpdateVideoFilter` and source/destination rectangles remain authoritative.
**Produces:** Standard processes at source size, then one native spatial fit and valid packing for the actual selected target. The new native selector is qualified in isolation, not activated globally yet.

- [ ] Pin R01-R19 against the native oracle, including adjustment Off, empty whitelist, stale entry, fractional rate, DCI and pending target. Baseline mismatch is RED; unavailable transport is tested separately from native selection.
- [ ] Add source/target combinations G01-G18 to the real Standard boundary, including P5 IPT and read-after-cancel/source lease tests. Assert no hidden UHD surface for admitted 1080-to-1080 fitting.
- [ ] Replace Standard's final spatial routing through the pinned native adapter. Preserve native Auto and saved choices; no generic RGB8 intermediate or extra P5 color conversion. Keep unchanged UHD/1:1 fusion when applicable.
- [ ] In a temporary isolated qualification probe/build, bypass the CB1 UHD/adjustment-Off override and validate actual Standard targets through existing `SelectOutput` capabilities/reasons. Keep production selection unchanged until Task7; no unmigrated route may encounter an expanded target through an intermediate candidate. Pending startup never becomes a persistent unsupported/source-type change.
- [ ] Run selection/spatial tests, FEL-setting controls and full integration/engine suites. Expected: native selection parity, exact identity bypass, correct requested/effective filter and route.
- [ ] Cross-link Kodi, screen Standard P8/P5 on both hosts across admitted output sizes in the isolated probe/build, plus current UHD production controls; reject silent fallback as a pass. Record frame timing, cadence gaps and actual target. Remove the temporary selection bypass after qualification.
- [ ] Remove replaced Standard branches/intermediates, stage/verify, repeat fidelity and HDMI timing after cleanup, then commit the coherent route.

## Task 4: Master reference geometry and exact target support

**Files:** Existing Master/P5 owners and adapter admission; `master_reference.c`, `profile5_images.c`, reference scaled-output tests and native selection/spatial tests.
**Consumes:** Native selected output/rectangles and target-aware packing; unchanged reference reconstruction/filter contracts.
**Produces:** Master retains exact reconstruction and metadata, then uses the single native Kodi final scaler. Existing IPT preference stays build-gated as before.

Non-UHD target checks use the same isolated qualification mechanism as Task3.
Production mode selection remains unchanged until Task7.

- [ ] Preserve same-mapping frozen Master pixels/metadata on both GPUs before any change; do not weaken an existing failing witness to hide it.
- [ ] Add G01/G05/G08/G10/G13/G16/G17 and T01-T10 Master controls with independent packing/reference oracles for genuinely new mappings.
- [ ] Preserve exact source-grid reference reconstruction and chroma/FEL filters, then route final picture fitting through the same actual Kodi scaler used by the other modes. Resized-output controls use native Kodi interpolation as their oracle; do not retain a competing Master final scaler.
- [ ] Test mode changes, failure with recovery Off/On, pending prepared frame with replaced target and P5 direct IPT. Expected: no false Master success, no silent Standard route, no source relabeling.
- [ ] Run suites, exact full-carrier controls, then actual admitted HDMI target/perf controls. Clean and repeat after cleanup before committing Master.

## Task 5: Remaining DV-input modes, individually

**Files:** Existing Adaptive, HDR10 Basic then Expert, existing HDR10+ consumer owners; current per-mode tests. Native adapter and target transport are reused, not duplicated.
**Consumes:** Tasks1-4's native final-fitting and actual-target contracts; existing algorithms, prediction inputs and source analysis.
**Produces:** D09, then D10, then D11, then D12 on the same spatial contract, each separately qualified before the next.

Keep non-UHD activation in isolated qualification builds until Task7. Existing
production target selection and its UHD controls remain active between routes.

- [ ] For the current mode, pin source-grid treatment and final-fit identity/crop/target observations and its established image/metadata baseline; show the old redundant or fixed-target behavior failing a targeted test.
- [ ] Replace only that mode's orchestration using native final geometry and the shared adapter. Do not change curves, trims, TV limits, analysis normalization, source metadata or validated vendor recipes.
- [ ] Test black bounds/nits, L5, overlay/subtitle placement, target generation and cancellation. HDR10 keeps at least10-bit output and existing chroma adaptation, not DV's packed-RGB8 rule.
- [ ] Run corresponding existing GPU oracles, all integration tests and actual route/admission checks. HDR10+ packet tests are not a claim of HDR10+ TV validation without a sink.
- [ ] Measure 30fps, relevant 60fps and GUI controls; clean replaced routing and repeat after cleanup. Commit that mode before opening the next.

## Task 6: HDR10-input AI routes and untouched native exclusions

**Files:** Existing HDR10 AI owners, `hdr10_ai_source.c`, `hdr10_ai_transport.c`, `hdr10_ai_enhanced.c`, `resolution_contract.c`; no new model or HDR10+-to-DV feature.
**Consumes:** Same native final fit; existing Reference AI then Adaptive AI policies and source-grid analysis.
**Produces:** D13 then D14 with source-normalized L1/L3 and unchanged model/curve; D15 remains native.

Use isolated non-UHD qualification until Task7. Include container regressions
D16-D21 without changing demux or stream assembly.

- [ ] Pin raw analysis inputs and predictions, active-expansion versus identity states, then actual final target. Expected RED on any inherited fixed-output/double-fit boundary, not on the model itself.
- [ ] Route Reference AI first, then Adaptive AI only after Reference qualifies. Retain existing startup/pending/prediction ordering and fallback deadlines; no new buffered-lookahead policy.
- [ ] Test mode/filter change during preparation, stop/seek, overlays and no stale-generation commits. Confirm source metadata is not overwritten by current output capability.
- [ ] Run suites and paired timing for actual active routes, preserving native SDR/HDR10/MVC/disabled controls. Do not count an AI fallback or identity shortcut as active AI performance.
- [ ] Remove old per-resolution routing, clean, repeat and commit each route separately.

## Task 7: Atomic native-selection activation, UX and real interaction

**Files:** Existing playback info/settings/quick-panel, source info and diagnostics owners only where an observed regression demands it; no skin code or new settings framework.
**Consumes:** Native actual selection/filter, source/output dimensions, existing `OutputSelection`, `OutputReason`, prepared/committed identity and target generation.
**Produces:** Native selection enabled only after all reachable routes are ready; U01-U11 and L01-L12 without duplicate scaler UI, source/output confusion or log flooding.

- [ ] Gate activation on completed Tasks2-6 and every reachable CB1 route's actual-target fitting/admission controls, including container and vanilla/stereo exclusions. If any route is unready, leave global production selection unchanged; do not compensate with a new route-specific quality/fallback mechanism.
- [ ] Remove the global CB1 UHD/adjustment-Off override and its obsolete force-UHD assertions in one coherent activation change. Run the real native oracle R01-R19 and route matrix together; no remaining current route may retain fixed-UHD spatial assumptions.
- [ ] Remove temporary selection probes/flags from production artifacts. Re-run full suites and actual admitted HDMI target checks for all affected routes before this globally activated candidate is considered usable.
- [ ] Exercise native per-file/default filter persistence and upgrade behavior; assert no new independent CB1 upscale setting is created.
- [ ] Report actual final scaling versus independent FEL work; hide irrelevant rows. Master shows its reference policy without overwriting saved native settings.
- [ ] Test native selection startup, filter changes, failure, retry after settled mode/hotplug and restoration to GUI. Preserve existing capability fallback, not a new resolution-forcing retry tree.
- [ ] Run subtitle black-bar/notification/L5, O cycling, pause/play/seek/home/stop/restart journeys at native1080 and UHD. Confirm no tiny lower-left image or stale viewport/FBO; preserve native screenshot behavior and explicitly retain existing DV capture limitations (U11).
- [ ] Recheck movie exactness outside UI footprints and full-raster metadata policy; no screenshot or analysis readback added solely for telemetry. Clean and rerun.

## Task 8: Whole-preview cleanup, complete image and qualification

**Files:** Build version/source receipts, final docs and actual replaced render owners. No new feature.
**Consumes:** All previously qualified routes and case results, not assumptions from the headless spike.
**Produces:** Complete qualified RC1 PreviewG image/source receipt, preserved older checkpoints, no publication.

- [ ] Audit and delete orphaned resolution-only branches, unused buffers/helpers, old force-UHD tests and failed trial flags. Keep genuine protocol, precision, backend and lifetime guards.
- [ ] Verify `config/cb1-versions.json` release version/tag/image consistently identify PreviewG; update actual build stamps and receipts. Fail packaging on stale PreviewE/F identity.
- [ ] Run `python3 CB1/tools/verify.py`, native patch-application/staging checks, the full engine CTest and `python3 -B -m unittest discover -s tests/cb1 -p 'test_*.py' -v` with the established pinned-source environment. Record actual counts/skips, not historical fixed totals.
- [ ] Cross-link and compile the complete image through existing build tools. Verify image/source hashes, version, boot artifacts and source-lock association before any test installation.
- [ ] Qualify N100 and AMD3200U case by case: short failure screens, then repeated longer cadence windows and complex interaction. No forced clocks, no silent fallback, async On; GUI timing separate. Minimize TV use and restore all test settings.
- [ ] Compare to the preserved baseline using actual source/output/route/filter identity. V03 compares modes that actually run, not fallback or separately encoded source pixels as a fidelity oracle.
- [ ] Dispatch one independent whole-branch review; fix important findings with RED-to-GREEN plus green suites. Re-run exact Master/P5 and relevant performance checks after cleanup.
- [ ] Finish only with explicit Pass/Fail/Pending/Hardware-unavailable results for the matrix. No image/repo publication; missing NVIDIA/HDR10+ physical validation remains explicit.

## Framing-stage verification and execution ruling

The use-case matrix covers all five Review Focus risks through Tasks1-8. Task1
is a deliberate implementation-adoption gate: its exact interop cost/signature
decision must be recorded before any downstream caller is changed. Task7 is the
global-selection gate: do not expose unmigrated routes to new targets during
Tasks3-6. Do not guess an engine callback framework in advance of the first proof.

The user approved native ownership and asked for a new preview plus precise
framing. This commit prepares PreviewG identity/design/cases/plan, not rendering
integration. Inline execution and a final independent review remain the selected
method. Review this expanded plan before implementing its atomic transport and
selection changes; no additional equivalent-change approval prompts between its
subsequent tasks.
