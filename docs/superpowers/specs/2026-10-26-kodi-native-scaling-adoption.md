# Preview G: native scaler adoption evidence

Status: native adapter and target-aware rendering implemented in the working
candidate. Global native mode selection is activated in source, not yet qualified
as a complete image. No new image installed or published. HDMI qualification and
final review remain pending.

## Native boundary

Use original Kodi filter classes and kernels before DV transport packing. No
lighter replacement, modified filter or custom fused interpolation is selected.
Keep Master reference precision and native per-video filter selection separate.

The existing bridge's GetPQTexture() can materialize UHD. It is not a valid
source-grid handoff by itself. The native handoff must preserve the actual
processed component domain, crop, precision, current picture/target identity and
source retirement lifetime. The adopted synchronous callback accepts the already
processed source and target `pl_frame` and returns one borrowed FP32 fitted frame.
It belongs to the existing Kodi Context and retirement fences, with no new queue.
Identity fitting bypasses it; rejection never selects another scaler.

Master remains exact before fitting. As explicitly approved, intentionally
resized Master pixels follow the actual unchanged native Kodi filter, not the old
CB1 scaler. Existing 1:1 reference controls remain independent.

## Fresh checks

- Real selector witness R01 fails with the current CB1 UHD override and passes
  with only that branch bypassed in memory. Product selection unchanged.
- Engine baseline: 209 passed, 11 skipped, zero failures out of 220 CTest cases.
  The hardware-dependent skipped cases are not counted as passes.
- Pinned N100 and AMD3200U: 12 GPU baseline witnesses each passed, covering
  source-grid Standard, Adaptive, HDR10 and AI, P5 and Master YCC/IPT controls.
- Actual original Kodi Shader/VideoFilter class lifecycle compiled and ran on
  both GPUs. The file-loader shim preserves the native GLSL version/define order.
- A private 1080p Standard witness ran source-grid CB1 reconstruction, original
  Kodi DefaultFilterShader and the existing final CB1 transport on both GPUs.
  It is not a full HDMI movie cadence or compatibility result.
- Installed kernel/system/Kodi/libplacebo/settings hashes remained unchanged.
  Temporary payloads were removed from the owned remote directories. TV not woken.

## Measured pass cost

Serialized median, 16 measurements after four warm-ups, synthetic FP32 data.
These are not movie frame times, FPS or HDMI headroom.

| 1080p to UHD operation | N100 | AMD3200U |
|---|---:|---:|
| Actual native bilinear filter then existing transport pack | 17.727 ms | 21.478 ms |
| Private fused interpolation comparison, rejected for integration | 7.201 ms | 5.271 ms |

The separate FP32 target occupies 132,710,400 bytes. Native lifecycle, state,
precision and whole-pipeline timing must qualify any required intermediate.
Fused comparison output matched on the tested N100 pattern but differed on AMD
by up to one 12-bit luma code and two chroma codes after removing the metadata
parity bit. This does not establish Master equivalence or a visual movie result.

## Concrete integration hazard reproduced

The old CB1 RGB hook can replace an already fitted texture with the earlier
source-sized texture. The trial reproduced libplacebo's no-op-scaler size
assertion. Removing that obsolete source hook from the private post-fit call,
while retaining packing and metadata hooks, made the same witness pass on both
GPUs. Production migration must remove the old ownership exactly once rather
than stack native fitting on top of the old spatial routing.

Remaining gates: real geometry/crop/orientation and native Auto admission,
borrowed-resource/state restoration, P5 domain handoff, Master exact controls,
and complete accepted HDMI playback after integration and cleanup.

## Integrated target checks

- Real native adapter on both GPUs: Master, Standard, Basic, Expert, Adaptive,
  Reference AI and Adaptive AI at UHD, 720p, 1080p and 1440p targets.
- Additional P5 Standard/Master target witnesses and a 4K Adaptive-AI source
  reduced to the same targets pass. These are synthetic functional tests, not
  movie timing or HDMI capability results.
- The AMD 4K Adaptive-AI constant witness differs by one rounded 12-bit luma code
  after native fitting. Its private check bounds this specific non-Master case;
  Master tests are not relaxed. Chroma bytes and alpha match this witness.
- New native-source checks exercise EGL surface dimensions, stale-target pack
  rejection, overlay wrapping/size changes, native filter admission and native
  whitelist/override/adjustment-Off parity.
- A checkpoint engine suite passed 218 cases, with 15 explicit hardware skips
  out of 233. An earlier native-integration suite passed 190 checks. Both must be
  rerun after the final selection/cleanup edits; these counts are not completion.
- Latest integrated verification: 220 engine passes, 15 explicit hardware skips,
  zero failures out of 235; 193 integration passes; cross-linked Kodi succeeds
  after native selection activation. All 30 Kodi patches replay with fuzz
  disabled on the SHA-verified source archive; twelve compiled owners match.
- Basic/Expert crop witnesses additionally pass with the actual native adapter
  on both GPUs. Twelve private functional cases run per machine without changing
  installed image/settings hashes.
  Complete image construction, full-frame fidelity oracle, physical target
  admission, interaction and cadence/performance remain pending.
