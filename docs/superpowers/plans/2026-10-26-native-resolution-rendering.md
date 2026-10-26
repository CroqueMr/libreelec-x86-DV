# Native-resolution rendering implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, task by task, with one independent final review. Steps use checkbox syntax for tracking.

**Goal:** Replace resolution-specific spatial routing with source-grid processing and late output fitting, without regressing 4K or exact Master.

**Architecture:** Reuse current rendering entry points and mode algorithms. Separate decoded source grid from displayed geometry and carrier; reuse source-sized intermediates only when a real pass boundary needs one. Preserve exact 4K fusion and backend recipes.

**Tech Stack:** C, C++, GLSL, FFmpeg, pinned libplacebo, Kodi/LibreELEC, WSL cross toolchain; existing Python test/SSH harness.

**Spec:** docs/superpowers/specs/2026-10-26-native-resolution-rendering-design.md (approved 2026-10-26).

## Global Constraints

- Frozen source ac554732636da0bebc5d29d816e3b13ae2c2c145; active isolated branch candidate/rc1-preview-f-native-resolution.
- Master: zero changed film pixels and metadata for identical source/output/backend; no relaxed rounding budget.
- No new non-Master approximation, model/curve change or resolution-specific quality tier.
- Keep Intel/AMD recipes, P5 direct IPT, exact FEL filters and current fences/retirement.
- No new queues, forced clocks, Fast/Auto selection, driver/audio/vanilla changes or publication.
- Master recovery default Off; qualification Off, async On, verify actual accepted circuit.
- Same source-grid processing contract for 1080p, 1440p, cropped pictures and 4K; carrier constants are not source-grid dimensions.
- Zero missed presentation intervals at 30fps; 1080p should match corresponding 4K cadence where 4K holds 60fps. Do not promise active Adaptive AI60 when its 4K baseline already misses.
- User approved direct execution and circuit-by-circuit qualification. No further equivalent-change approval rounds.

## Files and responsibilities

- CB1/src/dvbridge_render.c: geometry/target selection, mode prepare, final resample/pack, resource lifetime. Keep public signatures.
- CB1/src/dvbridge_render.h: update ownership comments only if public output contract actually changes.
- CB1/tests/resolution_contract.c: source-grid boundaries, final output and cancellation; avoid pinning obsolete pass count except duplicate final work.
- CB1/tests/profile5_images.c and master_reference.c: full carrier, metadata, P5 and exact Master.
- CB1/tests/scaled_adaptive.c, hdr10_ai_transport.c and reference_scaled_output.c: existing independent scale/domain/orientation controls.
- Pinned libplacebo native-transport patch: change only if the shared scaler boundary cannot be expressed through existing hooks, with unchanged reference pixels.
- Existing owning Kodi patch: only genuine caller/consumer geometry assumptions, no skin code.
- config/cb1-source-lock.json and CB1/config/owned-sources.json: matched receipts via existing stage.py/cb1-stage verification.
- Existing work/rc1-a-f-20261024 helpers: reuse compile_witness, gpu, measure, native-edit, stage, verify-native, final-state. One replaceable private binary, compact logs, no large media duplication.

## Review Focus

1. Source crop, L5, flip and output letterbox must not be applied twice or treat a chroma plane as a 1080p source.
2. Source-size surface replacement/cancellation must not release a decoded import before its final GPU read.
3. GUI or RGB compatibility consumers must not cause a second treatment/scale or pollute film statistics.
4. P5 IPT and Master exactness must not inherit Standard precision, extra RGB conversion or mutable Fast.
5. Adaptive AI identity and active-expansion paths must be compared separately, with unchanged model feature normalization.

All five are assigned below to concrete existing test owners.

### Task 1: Standard source-grid boundary, including P5

**Files:** Modify CB1/src/dvbridge_render.c; Test CB1/tests/resolution_contract.c and profile5_images.c; update matched receipts.
**Interfaces:** Consume existing render_picture/render/render_packed_overlay signatures and dvbridge_geometry. Produce source-sized reconstruction feeding the existing final fit/pack; no new public API.
- [ ] Add source-grid assertions to the Standard resolution contract: reconstructed target width/height equal source width/height; source-domain transport remains source-domain; final carrier/candidate geometry stays 3840x2160. Test cropped/flip and duplicate RGB consumer where appropriate.
- [ ] Run resolution_contract --case standard on both GPU backends and watch current reconstruction-grid assertion fail; retain existing HDR/Adaptive controls.
- [ ] Replace only Standard's scaled spatial orchestration using current reconstruction params and the final packer. Use one reusable native intermediate when required; no packed-carrier interpolation. Keep full-frame 4K route unchanged.
- [ ] Exercise profile5_images native 1080p/1440p, cropped and original-size placement, both orientations. Compare complete carriers/metadata and preserve established P5 precision.
- [ ] Run engine/integration suites, cross-link Kodi, run short 1080p60 Standard/P5 and matched 4K60 controls on both hosts. If gain is absent, identify pass costs before adding optimizations.
- [ ] Simplify, remove replaced Standard routing, stage/verify and commit a coherent working circuit.

### Task 2: Master exact native-grid storage and final fit

**Files:** Modify dvbridge_render.c; Test profile5_images.c, master_reference.c and resolution_contract.c.
**Interfaces:** Consume Task1's spatial boundary; retain dvbridge_render_master_reference and dvbridge_render_master_reference_ipt signatures, metadata and target contracts.
- [ ] Pin exact native/cropped output with deterministic varying ramps, edge/chroma phases, flip and L5; capture frozen full-carrier/metadata checksums on each actual GPU before changes. Assertions also require no premature target release.
- [ ] Add a failing check for avoidable full-carrier reconstruction backing/materialization on scaled Master. Use real GPU boundary observations, not source-text assertions.
- [ ] Reuse source-grid storage and late fitting only where exact output controls remain identical. Do not move a nonlinear operation across interpolation or weaken the reference oracle.
- [ ] Run complete exact witnesses and compare frozen hashes, repeat 4K and P5 controls; verify both Master output preferences remain correct.
- [ ] Measure 1080p60, 4K60 and FEL30, clean failed trials, repeat tests after cleanup, stage/verify and commit.

### Task 3: Authored Adaptive spatial orchestration

**Files:** Modify dvbridge_render.c; Test scaled_adaptive.c, resolution_contract.c, p5_adaptive_images.c.
**Interfaces:** Reuse source-grid/final-target boundary, current policy prepare/poll/resolve and retirement owner.
- [ ] Add/extend real GPU tests for native reconstruction/expansion, final scale exactly once per accepted frame, stable ceiling/black bounds, crop/flip and repeated RGB resolve.
- [ ] Watch the old full-1080p-only sampler/prepare admission fail a same-contract non-1080 native-grid case. Retain ratio/capability guards that protect exact sampler behavior.
- [ ] Replace dedicated 1080p orchestration; preserve measured vendor PQ/storage recipes, metadata guidance and anti-pumping. Avoid new 4K intermediate unless a real consumer needs it.
- [ ] Exercise withheld fence cancel/seek/stop and overlays; run suites plus paired GPU/HDMI controls at 1080p/1440p/4K and FEL30.
- [ ] Simplify, delete orphaned Adaptive branches, stage/verify and commit only measured useful changes.

### Task 4: HDR10 Basic then Expert

**Files:** Modify dvbridge_render.c; Test resolution_contract.c, reference_scaled_output.c and reference_scaler.c.
**Interfaces:** Preserve dvbridge_render_hdr10_rgb and policy/direct variants. Reuse the same final fitting boundary without changing tone curves or quantization.
- [ ] Pin source-size processing and late output for both modes, correct black borders/ceiling and final bit depth; ensure repeated output request does not rerun treatment.
- [ ] Reproduce redundant materialization or old spatial routing with a failing boundary check before deleting it.
- [ ] Simplify Basic first, then Expert, keeping each independently functional. Keep Expert trim domain, maximum nits and final clipping/quantization order.
- [ ] Run scaled-output independent oracle, 600/1000/2000/10000-nit ceilings, GUI/black-bar and lifetime controls; measure both backends without silent fallback.
- [ ] Run suites, clean and revalidate each mode, stage/verify, commit separately where meaningful.

### Task 5: Existing HDR10+ consumer compatibility

**Files:** Existing Kodi HDR10+ owner patch and tests only if demonstrated; cb1_hdr10plus_analysis.c only for a proven size assumption.
**Interfaces:** Consume the common processed RGB output with explicit source/output geometry; keep existing metadata serialization and output admission.
- [ ] Run native-size/cropped analysis and packet normalization, unsupported-display fallback and actual route admission tests.
- [ ] If a consumer assumes carrier dimensions for source analysis, add a failing normalized-statistics test and fix only that boundary.
- [ ] Preserve 4K packet/output controls; run suites and stage/verify. Record lack of HDR10+ display, never claim real HDR10+ HDMI qualification.

### Task 6: HDR10 Reference IA then Adaptive IA

**Files:** Modify dvbridge_render.c only unless caller geometry is wrong; Test hdr10_ai_transport.c, hdr10_ai_enhanced.c and resolution_contract.c.
**Interfaces:** Existing prediction/prepare/resolve APIs and model; explicit native source picture and final carrier. No new model features.
- [ ] Pin reference transport without active expansion, then active Adaptive and identity paths separately. Compare raw L1/L3 prediction inputs/results before and after.
- [ ] Watch a source-size identity/prepare or double-final-work regression fail, without counting a 4K no-headroom shortcut as active expansion.
- [ ] Generalize the spatial boundary with original color domains and current source-normalized analysis; do not change model, curves, deadlines or fallback policy.
- [ ] Verify full carrier/matched metadata, RGB compatibility, repeated resolve and in-flight cancellation. Run 1080p/4K at both TV2500 and5000, both backends.
- [ ] Run suites, simplify and remove old routing after each IA mode qualifies; stage/verify and commit.

### Task 7: Whole-branch cleanup, image and qualification

**Files:** Documentation, matched receipts and existing build/version owner; no new rendering feature.
**Interfaces:** All previous existing entry points remain, with consistent source-grid/output geometry and unchanged user-visible modes.
- [ ] Remove unreferenced resource fields and helpers, old 1080-only CTest implementation variants, and failed prototypes; preserve behavioral oracles and genuine backend/ratio guards.
- [ ] Run full 186-integration baseline suite and complete engine suite (updated counts recorded), pinned patch application/staging checks, cross-link and full image build.
- [ ] Verify output version PreviewF, source receipts, artifacts and boot/initramfs checks using existing build tools. Never overwrite frozen PreviewE artifacts.
- [ ] Qualify N100/3200U circuit by circuit: 1080p/4K, 30/60 input, P5/P8/FEL, crop/flip, actual output route, no fallback, short failure screening then longer repeats and complex interaction journey.
- [ ] Compare FPS, HDMI gaps, GPU ms/picture, load and margins to frozen audit; keep remaining capacity limits explicit. Restore user settings and check kernel GPU health.
- [ ] Dispatch one fresh independent whole-branch reviewer; fix important findings with RED→GREEN and rerun suites. Clean this plan's scratch artifacts only after proof is retained. No push or release.

## Self-review and execution ruling

Spec sections map to Tasks1–7. All public signatures remain existing; source-grid ownership/final target is shared, not a new graph framework. Test/source synchronization goes through current staging helpers. The same source cannot be compared across unrelated files as a pixel oracle.

User's 'Oui go' approves direct execution of the reviewed design. This plan is its implementation breakdown, not a new approval round. Begin Task1 after writing the ledger. Any newly necessary change to algorithms, quality budget, security or publication remains outside authority.

