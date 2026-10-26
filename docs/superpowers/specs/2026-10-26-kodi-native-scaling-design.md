# Kodi-owned resolution and final scaling

Status: architectural contract approved in conversation on 2026-10-26; expanded
case matrix and execution plan prepared for RC1 Preview G. Rendering integration
is not implemented by this document. Supersedes the earlier fixed-4K-carrier
spatial assumption only when its replacement has passed the gates below.

## Preview and scope identity

- Preserved source: `832d970cc7`, checkpoint branch
  `checkpoint/rc1-preview-f-before-native-kodi-scaler-20261026`.
- Work branch: `candidate/rc1-preview-g-kodi-native-scaling` in the existing
  isolated worktree. Preview F was a source checkpoint, not a completed image.
- New build identity: `DV-R1.0.0-RC1-PreviewG`; future tag
  `R1.0.0-RC1-PreviewG`; no publication requested.
- Existing installed Preview E images remain unchanged. Do not relabel them G.
- Detailed cases: [case matrix](2026-10-26-kodi-native-scaling-cases.md).
- Execution: [implementation plan](../plans/2026-10-26-kodi-native-scaling.md).

## Goal

Use Kodi's output mode selection, picture geometry and native spatial scaler as
far as possible. CB1 processes the decoded source grid, then the picture is
fitted once to the actual output before Dolby transport packing. A 1080p picture
displayed pixel-for-pixel in a 1080p output must not take an internal trip to 4K.

Keep the frozen PreviewE and current source-grid checkpoint `832d970cc7`.
No publication, driver change, AI/model/creative-curve change, new quality tier,
new frame queue or forced clock. Preserve both vendor-specific processing
recipes and the existing explicit recovery policy, default Off.

## Evidence and alternatives

The current CB1 resolution selector returns a progressive UHD mode before the
normal whitelist. A source-based RED test reproduces an ignored explicit 1080p
entry; an in-memory trial without the UHD override restores it. The packer,
scanout validation, output geometry, masks and UI still assume 4K. Merely removing
the resolution override would activate unsupported rendering targets.

Native Kodi shaders plus its compiled kernel generator completed seven
geometries and six filter variants on both GPUs without waking the TV. Direct
native bilinear is approximately as expensive as LP bilinear, rather than a new
order-of-magnitude gain. Native and LP Lanczos variants are not identical; native
full Lanczos is substantially more costly than the optimized native variant in
this isolated benchmark. Native bilinear matches the tested N100 control exactly
but differs by up to one rounded 12-bit code on AMD. This is not Master proof.

Approaches:

1. A separate CB1 resolution/upscale preference: rejected, conflicts with Kodi.
2. Always scale again through a full-screen Kodi pass: rejected as a default,
   duplicates work and may lose the measured performance benefit.
3. Kodi-owned final fitting using existing native shader/kernel operations before
   CB1 transport: selected direction. Reuse existing interpolation/fusion where
   compatible; add a real intermediate only when a demonstrated boundary needs it.

The prototype and source audit are in
`work/rc1-a-f-20261024/KODI-NATIVE-SCALER.md` outside this repository.

## Ownership

- Kodi selects the actual output resolution and refresh rate through its native
  adjustment, whitelist and override rules. CB1 must not silently force 2160p.
- Kodi supplies the source crop, display rectangle, aspect, zoom and orientation.
  Use those values, not a second independent rectangle calculation.
- CB1 reconstructs/processes at the decoded source grid, with its existing color
  representation and metadata. Preserve native P5 IPT and Master precision.
- The final spatial stage reuses native Kodi operations, then transport packing
  follows at the selected target dimensions. Never scale packed tunnel bytes.
- Reuse the native scaling preference. Do not add another CB1 upscale switch.
  Keep Kodi's existing Auto filter-admission policy, including its source-size,
  frame-rate and hardware conditions. For the ordinary 1080p case this resolves
  to bilinear; do not redefine all Auto inputs as bilinear or change the global
  vanilla default. Preserve saved explicit choices and distinguish actual
  Lanczos variants.
- Execution clarification: use the actual native Kodi scaler, not a lighter
  replacement, modified kernel or rewritten fused filter. Native shader
  lifecycle/call sites remain authoritative. The private fused-interpolation
  timing is comparative evidence only, not an integration candidate.
- Only spatial settings enter this handoff. Do not reapply native SDR conversion,
  brightness/contrast, color management, range conversion, tone mapping or
  output quantization to already processed CB1 component data.
- FEL enlargement remains independent: align EL to BL before reconstruction,
  even when no final video enlargement is needed.
- Vanilla/fallback and MVC/3D remain native and outside CB1.

## Selection, admission and startup order

There are separate authorities, not one combined "4K DV mode" boolean:

1. Preserve the source identity and all DV metadata independently of current
   output readiness. A mode change must not relabel the source HDR10 or remove
   stored playback settings.
2. Kodi's normal mode finder selects the actual target using user adjustment,
   whitelist, overrides and hardware mode list. With adjustment Off, preserve
   native behavior; with an empty whitelist, preserve the native default rules.
   Do not force source-sized output merely because the source is 1080p.
3. Wait for that selected mode/context to be settled through the existing native
   lifecycle. A temporary 0x0 drawable, an old mode or pending atomic commit is
   Pending, not definitive unsupported hardware. No new arbitrary startup delay.
4. Validate the current target's dimensions, driver/connector, actual surface
   format, bit depth and required transport against existing capabilities. Use
   physical output pixels, not the GUI logical coordinate grid. Never infer DV
   from a whitelist entry alone, nor reject all sources based on an old mode.
5. Prepare source-grid processing, then final spatial fit and transport with
   one matching picture identity and target generation. Reuse the existing
   readiness/fence/retirement path. Admit and announce only the actual committed
   route; keep incompatible/stale targets out of scanout.
6. For a definitive failure, use existing `DVBRIDGE::SelectOutput` and its
   `OutputReason`. Retain its settings and route rules, not a new fallback tree.
   Show requested versus effective route/reason. Do not secretly change Kodi's
   selected resolution to make DV work. A later valid target can be re-admitted
   without toggling persistent settings.

Existing capability policy remains the authority: native HDR10 requested from
HDR10 input stays vanilla; unavailable HDR10-to-DV returns vanilla with a reason;
DV input can use the established HDR10 Basic/vanilla fallback according to its
current capability policy. Master with recovery disabled must not be presented
as Standard. Do not describe a failed requested route as a successful DV test.

## Boundary contract and representation

Reusing Kodi behavior does not authorize passing an 8-bit display screenshot
between stages. The handoff must identify the source texture/planes, visible
source crop, component representation (including P5 IPT), transfer/primaries,
precision/range, destination rectangle, actual target dimensions, orientation,
picture identity, target generation and borrowed resource lifetime. Use current
`pl_frame`, `pl_tex`, geometry and retirement primitives wherever sufficient;
no new generic graph, independent scheduler or duplicate frame queue.

The native adapter belongs in Kodi, not inside the reusable CB1 engine. Reuse
the original `CConvolutionKernel` and spatial shader source rather than copying
their implementations into CB1. The adoption prototype must establish whether
native spatial reuse can retain current scale/pack fusion. Do not add an
unconditional output-sized FP32 write/read solely to claim native reuse.

Source-grid treatment and carrier indexing must be changed coherently. Carrier
stride/flip, metadata coverage, L5/UI mapping and packed format are parameterized
from the validated actual target, not inferred from the source or a global 4K
constant. Preserve the Dolby RGB8 tunnel's 12-bit payload contract; ordinary
HDR10 output still uses its established minimum-10-bit policy. These are
different bit-depth contracts.

If native exact shader reuse imposes a measurable extra pass, quantization or
Master error, stop that integration trial and report it. Keeping native mode,
geometry and preference ownership does not justify disguising a different
libplacebo Lanczos as Kodi Lanczos, or degrading Master to make a test pass.

## Settings, diagnostics and readiness criteria

Use the native per-video scaling setting, saved per-file override and native
"set as default" mechanism; do not overwrite them during migration. Auto keeps
native semantics. The intended default for the ordinary 1080p case is bilinear,
not a new global forced bilinear policy for every source. Unsupported controls
must not pretend to be applied; Master explains its reference spatial policy
without changing the saved native setting for other modes.

Keep FEL selection separate. The optional Player information rows report only
active final scaling and FEL work, with source/target dimensions and actual
filter. Identity fitting says no scaling or hides the row, never labels a copy
"Lanczos". Transition/failure logs include requested mode, settled target,
filter, domain, precision and route reason; no per-frame log flood.

All case IDs in the matrix require implementation coverage or an explicit
hardware limitation, never an invented pass. A complete image is qualified only
after source/patch verification, full suites, exact reference controls, actual
Intel/AMD HDMI timing and a post-clean repeat. No performance or compatibility
claim follows from the standalone prototype alone.

## Spatial behavior

| Picture and actual target | Required behavior |
|---|---|
| 1080p to 1080p | No final interpolation for a genuinely pixel-aligned 1:1 mapping |
| 1080p to UHD | Process 1080p, one late final enlargement |
| 1440p to 1440p | Same identity rule; no separate 1440p recipe |
| 1440p to UHD | Same processing, one late enlargement |
| UHD to 1080p | Process source, one final reduction |
| UHD to UHD | Preserve fused/identity path, no extra materialization |
| Cropped/nonstandard aspect | Follow Kodi placement and black borders without stretching |
| Zoom/fractional placement/non-square pixels | Resample only as Kodi's actual mapping requires |
| Window/output change | Refresh target geometry and retire old resources safely |

Apply this to actual admitted source/output dimensions, not a whitelist of
1080p and UHD constants. An EDID mode and a complete DV transport are separate
validation scopes: check both, do not remove real format/buffer constraints to
make a mode appear supported. Report a concrete incompatibility and retain the
existing route/recovery policy instead of silently changing resolution or mode.

## Reference guarantees

Master preserves exact reconstruction, chroma/FEL reference filters and metadata
before final picture scaling. The user explicitly confirmed on 2026-10-26 that
final enlargement/reduction uses the same unmodified native Kodi scaler as every
other mode. Do not retain a second Master-only final-picture scaler. Preserve
existing UHD Master pixels/metadata when no spatial resampling is required.
After intentional resizing, the oracle is the exact reconstructed input followed
by the actual selected native Kodi filter, not the previous CB1 interpolator.
New output dimensions require independent packing/parity/metadata and native
geometry checks; they do not inherit certification from a whitelist entry.

Keep source/processed color tags, component range, bit depth and GPU leases
explicit at the handoff. Avoid a generic RGB8 intermediate. Map source L5 and
UI footprints exactly once. Do not include the GUI, letterbox padding or final
carrier in source-picture brightness/AI statistics.

## Replacement order and verification

1. Finish the native handoff prototype: original Kodi interpolation/kernel code,
   real source/destination rectangles and precision-safe targets. Prove 1:1 bypass,
   up/downscale, crop/flip and no extra color/tone-map operation.
2. Generalize target/packet/flip/overlay/scanout handling coherently while
   retaining the existing production mode selector.
3. Replace Standard's final spatial ownership, including P5, before opening
   another circuit. Retain exact 4K fusion and compare the complete output.
4. Migrate remaining existing routes one at a time; retain Master reference
   algorithms and qualify new targets independently in isolated probes/builds.
   Keep global production selection unchanged until every reachable route is
   ready. Then remove the CB1 UHD override atomically and run the native selector
   and complete route matrix together. No permanent per-route selector flag.
   Preserve DCI/invalid-mode checks as validation, not hidden UHD selection.
5. Delete superseded fit/scale branches, unused intermediates and selection
   exceptions only after their last consumer has moved. No dead placeholders or
   experimental flags in production.
6. Run the existing engine/integration suites and patch/source-lock checks,
   exact Master/P5 controls, then short HDMI screens followed by stability
   repeats and pause/seek/O-menu/stop transitions on N100 and AMD3200U. Minimize TV.

Measure actual HDMI cadence, gaps, GPU busy time/load and readiness margins.
Standalone filter timings do not establish full-pipeline FPS or headroom.
Keep the installed images unchanged until an integrated candidate is qualified.

## Independent builder check

Read-only checks identified two framing points now addressed: preserve native
Auto semantics rather than a separate CB1 Auto-to-bilinear rule, and defer global
native-selection activation until all reachable routes have migrated. Temporary
new-target probes must not expose unmigrated routes in production. Precision,
transport eligibility and performance still require the stated measurements;
the review does not certify implementation.
