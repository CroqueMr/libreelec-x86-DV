# Algorithms and metadata

This reference describes **CB1 0.5 in the published R1.0.0 RC3 release** and the circuits listed in
[CIRCUITS.md](CIRCUITS.md). Equations describe the implemented processing
contract, not a certified reproduction of Dolby's proprietary display mapper.

## Pipeline and ownership

1. The player decodes and supplies GPU images, frame identity and FFmpeg metadata.
2. CB1 reconstructs the source, including matched applicable FEL residuals.
3. The selected circuit processes pixels, metadata, or both.
4. The player presents the result through the validated HDR10 or DV driver path.

Audio, subtitles, demuxing and playback timing remain player-owned. Metadata is
bound to stream, picture, policy revision and timestamp. Preparing a candidate
is not presentation: the corresponding state is committed after submission
through the presentation transaction. Seeks and mode changes invalidate stale
work rather than reusing metadata from a different picture.

## Variables and units

| Symbol | Meaning |
| --- | --- |
| `P(L)` | Normalized ST 2084 PQ value for luminance `L` in nits |
| `E(q)` | PQ EOTF returning nits from normalized PQ |
| `q` | A 12-bit metadata value, 0 to 4095 |
| `T` | Manual display-reference peak in nits |
| `M` | Source reference: DV source-max PQ decoded to nits, or HDR10 mastering maximum for AI Adaptive; not measured scene maximum |
| `S` | Scene-dependent strength multiplier |
| `Y` | Luminance in the current working gamut |
| `w` | Bounded interpolation weight between compatible anchors |
| `clamp(x)` | Clamp to the interval 0 to 1 |
| `H(x)` | Smoothstep polynomial `x*x*(3 - 2*x)` after clamping |

`H(a,b,x)` below means `H(clamp((x-a)/(b-a)))`. Unless specified otherwise,
`round` means nearest integer with positive half-way values rounded upward;
`round_even` uses ties-to-even. Code words and normalized PQ are distinct.

ST 2084 uses `m1=2610/16384`, `m2=2523/32`, `c1=3424/4096`,
`c2=2413/128`, `c3=2392/128`:

```text
p = (L / 10000)^m1
P(L) = ((c1 + c2*p) / (1 + c3*p))^m2
metadata code = round(4095 * P(L))
v = q^(1/m2)
E(q) = 10000 * (max(v-c1,0)/(c2-c3*v))^(1/m1)
```

Runtime float arithmetic and final integer quantization are separate stages.
libplacebo's linear working unit is 203 nits; this is a unit conversion, not a
display peak or an output brightness cap.

## Metadata use

| Metadata | Dolby Vision Reference | HDR10 conversion | Authored Dolby Vision Adaptive HDR Mapping |
| --- | --- | --- | --- |
| RPU reconstruction data | Reconstruct source pixels | Reconstruct before conversion | Same reconstruction as Reference |
| L1 min/max/average | Transport | Maximum/average guide scene mapping; minimum validated and retained | Guide expansion; transform authored scene descriptors through the applied curve |
| L3 offsets | Transport | Retained, not executed | Fold once; emit neutral offsets when the block is present |
| L2 CM2.9 trims | Transport | HDR10 Rendering Reference applies compatible primary controls | Guide luminance retention and color protection |
| L5 active area | Transport and mask borders | Preserve active-area geometry | Output geometry; full-raster signalling while overlays are visible |
| L6 HDR mastering | Transport | Source reference and static HDR descriptors | Retained if present; not relabelled as measured output |
| L8 CM4 trims | Transport | Retained; available L2 compatibility only | Guide luminance retention and color protection |
| L9 mastering primaries | Transport | Resolve source mastering gamut | Retained; no output signal-gamut override |
| L10 target descriptions | Transport | No full L8 creative render | Resolve source anchors; retained if present |

Raw and parsed CM4 fields must agree. Optional-field presence follows the raw
block length, not whether the value is nonzero. Unknown targets are not assigned
invented peak, black-level or transfer values. Duplicate or inconsistent data
is not presented as valid processing.

L1-only authored DV does not acquire fabricated L2/L8 trims. The selected Adaptive
path can expand it using neutral trim retention. Missing usable scene analysis
still preserves the source image/metadata pair; missing optional creative trims
alone does not disable reconstruction or expansion.

## Dolby Vision Reference

BL samples are reshaped using the RPU's piecewise polynomial or MMR mapping.
For applicable Profile 7 FEL, the timestamp-matched EL contributes the decoded
residual before color reconstruction. The LINEAR_DZ code-space residual uses:

```text
residual = 0                                      if rr == 0
residual = sign(rr) * ((abs(rr)-0.5)*scale+threshold) / 2^denom
```

The source YCC transform, offsets and linear color transform then reconstruct
the image. Applicable FEL is not treated as optional BL-only success.
MEL does not contribute a full enhancement residual.

The reconstructed image and display-management metadata are packed into the
DV HDMI transport. RGB8 is the byte container, not a reduction of the video to
ordinary 8-bit SDR. Scanout must preserve the packed bytes; color transforms,
range changes and dithering cannot be applied to that container as ordinary RGB.
The TV performs final TV-Led display mapping.

## Dolby Vision to HDR10 Rendering

HDR10 Rendering reconstructs the source, then uses libplacebo's spline tone mapper and
perceptual gamut mapper. Valid L1 maximum/average values guide scene processing;
otherwise the mapper uses static HDR descriptors. The reference derives from
valid source mastering metadata, not a manual TV peak.

Inverse tone mapping is disabled. A dim scene is not forced to reach the
mastering peak. The output is BT.2020/PQ with player-managed HDR10 signaling.
Source MaxCLL/MaxFALL are not relabeled as measured output statistics.

### Fixed libplacebo policy

| Parameter group | Values |
| --- | --- |
| Gamut | Perceptual; colorimetric gamma 1.8; soft-clip knee 0.70; desaturation 0.35; deadzone 0.30; strength 0.80 |
| Tone knee | Adaptation 0.4; minimum 0.1; maximum 0.8; default 0.4; offset 1.0 |
| Tone shape | Slope tuning 1.5; slope offset 0.2; spline contrast 0.5; exposure 1.0 |
| LUTs | Tone 256 entries; gamut 48 x 32 x 256; contrast smoothness 3.5 |

These are rendering coefficients, not user calibration measurements.

## Dolby Vision to HDR10 Rendering Reference

The frame-owned plan binds reconstruction, source descriptors, explicit tone
mapping, target gamut, compatible L2 controls and HDR10 signaling. Required FEL
must be paired; source metadata remains immutable.

Peak `T` (50–10000 nits), black floor `B` and gamut are independent from other
circuits' TV profiles. Black presets are OLED 0, LCD/Mini-LED 0.005 and projector
0.05 nit, or a custom 0–0.5 nit value. Presets estimate black; they do not measure it.
Disable the TV's additional dynamic tone mapping when using this player-led mapping.

### Tone and creative controls

The runtime uses raw valid L1 maximum/average without adding L3. L1 minimum is
validated/descriptive, not a display-black anchor. Missing/unusable L1 uses static
descriptors from the same frame. Malformed or contradictory metadata is rejected.

The native ST2094-10 curve compresses when the scene exceeds `T`; otherwise native
clip avoids inverse expansion. Both use the display-adapted range `PQ(B)..PQ(T)`.
FP32 tone LUTs have 1024 entries for compression or 4096 for clip.

Compatible L2 anchors bracket `T` and interpolate by PQ distance. With no upper
anchor the existing resolver can use a neutral mastering anchor. With no usable
L2, base mapping remains active. The three primary words shape the tone LUT:

```text
s = (c0-2048)/2048; o = (c1-2048)/2048; g = (c2-2048)/2048
x = (q-PQ(B))/(PQ(T)-PQ(B))
F(x) = x + x*x*(1-x)*(1-x) * (o*(1-x) + s*x - 4*g*x*(1-x))
q_out = PQ(B) + (PQ(T)-PQ(B))*F(x)
```

This signed curve fixes both endpoints and their unit tangents. Neutral controls
bypass it; no linear RGB SOP remains. Chroma uses bounded linear target-gamut RGB
and that gamut's luminance weights. Zero channels/luminance are guarded.

CM4 uses available L2 compatibility only. L3/L8 are not stacked onto the explicit
curve; L8-only sources do not claim a full CM4 creative render. Spatial and secondary
CM4 controls remain unexecuted in this runtime. The independent `cb1-cm4-v1`
scalar/spatial API is a separate numerical reference, not this runtime contract.

### Output

Kodi's native spatial scaling and final BT.2020/PQ carrier remain in place,
without a second scene tone map. The movie ceiling is rounded down to the accepted
integer output grid before GUI composition; it does not cap GUI brightness.
L5 bands retain nominal black. HDR10 metadata describes the virtual target
peak/black/gamut, not measured MaxCLL/MaxFALL; unknown content light levels are zero.
A target above the source does not automatically brighten the entire film.

This is an open player-led mapping, not the proprietary Dolby content mapper or
a claim of certified LLDV equivalence. The published RC3 implementation is in
`src/cb1_hdr10_expert.c` and the matched libplacebo tone-LUT patch.

## Authored Dolby Vision Adaptive HDR Mapping

`cb1-dve-pixel-v1` processes reconstructed linear BT.2020 pixels, then updates
scene L1/L5. Kodi and the engine expose one Adaptive HDR Mapping mode.
The equations here describe the supported metadata-guided expansion model,
not the licensed Dolby mapper. Native and HDR10 conversion
retain their separate contracts; AI Adaptive reuses the same scene-guided curve
with predicted guidance and no authored trims, as specified below.

### Source guidance

`M=E(source_max_pq/4095)` is the source bound; `T` is the configured display
reference. The stable output envelope is `max(M,T)`, not a measured panel peak.
Effective L1 applies normalized L3 once:
`round(L1+(L3-2048)*4095/2048)`.

Eligible L8 anchors take precedence over L2. Targets must resolve through known
presets or L10, use HDR PQ and match the configured gamut. Unknown extras do not
erase usable anchors. Missing controls stay absent. Two bracketing anchors use
PQ-distance weights; endpoints use the nearest anchor without extrapolation.
L2 has no authored gamut descriptor. Its scalar guidance uses the established
BT.2020 evaluation domain without rejecting P3-D65 or BT.709 display profiles.
Explicit L8 targets still require matching gamuts. Signal primaries stay BT.2020.

Each anchor is decoded and sampled in its own peak/gamut domain. Achromatic
slope/offset/power and present L8 midtone/clipping controls produce a retention
response `r(u)` bounded to [0.5,1.15]. Responses, not raw words, are blended.
Color-control magnitudes constrain added light; their signed creative grade,
global saturation and Tone Detail are not applied again.

For anchor peak `Ta`, weight `wa`, knot `u[k]=k/256` and a neutral-axis trim
operator with colour/detail controls disabled:

```text
x[k] = (10+(M-10)*u[k])/M
v[a,k] = trim_at_anchor((x[k]*Ta, x[k]*Ta, x[k]*Ta)).R
r[k] = sum_a(wa * clamp(v[a,k]/(Ta*max(x[k],1e-6)), 0.5, 1.15))
```

CM2.9 uses its primary trim operator; CM4 additionally uses present midtone
and clipping controls. `r[k]` is a guidance ratio, not a second creative pass
applied to the image.

### Expansion

For `u[k]=k/256`, build 257 knots. With `H` denoting clamped smoothstep:

```text
high = E(effective_L1_max/4095)
mid = E(effective_L1_average/4095)
S = H(100,400,high) * (1 - 0.5*H(0.04,0.30,mid/max(high,1e-9)))
C[0] = 0
exponent = 2 + 2*H(0.04,0.30,mid/max(high,1e-9))
C[k] = C[k-1] + (u[k]^exponent-u[k-1]^exponent) * (r[k-1]+r[k])/2
reference = min(M,max(100,high))
normalization = max(1e-9,lookup(C,(reference-10)/(M-10)))
A[k] = H(100,400,high) * max(T-reference,0) * min(1,C[k]/normalization)
B[k] = (1-H(M,1.5*M,T)) * S * 0.12*(M-10)
       * 16*u[k]^2*(1-u[k])^2*r[k]
extra[k] = A[k] + B[k]
```

The pixel shader linearly interpolates this table at
`u=clamp((Y-10)/(M-10),0,1)`. Highlights can expand when the display peak is
below the mastering bound but above the authored scene peak.
Dark scenes do not automatically reach T.
Missing usable L1 preserves the original image/metadata pair. With valid L1 and
no creative anchors, retention is one and trim-derived color restraint is neutral.
HDR10 AI uses this scene-guided curve with neutral retention.

Two global color coefficients and 65 circular hue samples restrain expansion
using original trim magnitudes and target-domain hue centers. An IPT/PQ chroma
gate preserves neutral grays. Restraint is bounded to [0.65,1]; no independent
hue rotation or saturation boost is applied. One RGB multiplier preserves
linear chromaticity. In IPT/PQ, let `I,Ct,Cp` be intensity/opponent channels:

```text
z = clamp(I/P(M))
gate = H(0,0.15, hypot(Ct,Cp)/I)             # zero if I<=0
severity = c0*abs(2*z-1) + c1 + hue_lookup(atan2(Cp,Ct))
restraint = max(0.65, 1/(1+0.5*gate*severity))
extra = interpolated_extra * restraint
```

`c0` and `c1` are weighted absolute log2 magnitudes of decoded anchor chroma
and saturation gains. Hue lookup combines the weighted absolute log2 secondary
saturation and absolute rotation divided by `pi/12`, using the CM4 circular
weights. Neutral grays bypass this colour restraint.

A continuous common-channel shoulder reserves headroom
above 90% of available gain. For positive luminance and peak channel, after
colour restraint:

```text
delta = extra/Y
h = max(0,T/max(R,G,B)-1)
knee = 0.9*h
width = 0.1*h
if delta > knee:
    tail = delta-knee
    delta = knee + width*tail/(width+tail)
RGB_out = RGB_in*(1+delta)
```

The BT.2020 luminance weights are
`(0.262700212011267,0.677998071518871,0.059301716469862)`.
Luminance <=10 nits and pixels outside L5 bypass expansion. The output shoulder
limits added light to T without reducing source values already above T.
The declared envelope remains `max(M,T)`. Transfer lookup/re-encoding may
still differ by the qualified one-code tolerance described below.

A whole-picture GPU guard selects identity if active luminance exceeds M
or any channel exceeds the envelope, allowing 0.01% plus 0.001 nit for FP32 PQ
decode error. Invalid/nonfinite source samples fail preparation. There is no
per-pixel mixture of expanded and unexpanded content.

### Temporal state and output metadata

Curve/color change shares a budget of
`0.5*dt*max(abs(T-M),0.12*(M-10))`. Only successfully presented matching
pictures advance state. Cancelled work and paused redraws do not advance it;
stream, display-profile and seek discontinuities reset it. Source-metadata revisions
do not bypass the authored curve's change budget. Metadata refresh flags alone
are not treated as scene cuts.

Authored-DV output uses `cb1-authored-scene-curve-v1`. Effective authored L1,
including L3 once, is transformed through the applied curve's neutral axis.
For an eligible effective 12-bit descriptor `c`:

```text
c_out = min(4095, c + max(0,round(4096*(P(curve(E(c/4095)))-c/4095))))
```

Descriptors at or below 10 nits and above the source mastering bound remain
unchanged; average is bounded by the updated minimum and maximum. Constant
authored guidance and an unchanged curve produce constant output L1, independent
of individual frame extrema. The average is a scene-descriptor approximation,
not an exact average of the nonlinearly transformed scene.
Emitted L3 is neutral after folding, preventing duplicate offsets. Authored
L2/L8 and other compatible metadata blocks remain intact. L5 describes the
output raster. Residual reconstruction is complete before this stage.
The declared processing envelope is `max(M,T)`, bounding the applied transform;
it is not a measurement of content or panel peak. Original source range,
transformed scene L1 and measured output remain safety floors.
Dense paired GPU statistics validate the pixels and source-bound guard; they do
not drive authored scene L1 frame by frame. The measured peak remains a safety
floor for the declared envelope; source-bound identity retains original metadata.
This scene model does not claim
equivalence to Dolby's proprietary analysis or guarantee TV panel brightness.
HDR10 AI Adaptive HDR Mapping retains its separate absolute-output analysis below.
The source-bound identity branch retains the original metadata/candidate and
recovers canonical PQ without expansion.
Expansion, source validation and dense statistics share one pass. Eight pixels
per lane amortize reduction barriers without subsampling. Any bound violation
discards the entire transformed scratch image before presentation. The changed
sum order is qualified to one logical 12-bit PQ code against the scalar mean.
Existing 4096-point FP32 transfer textures replace repeated PQ powers when
linear float sampling is available. The encoder uses fourth-root coordinates;
unsupported formats retain analytic PQ. Pixel/statistic differences are qualified
to one logical 12-bit PQ code. A 0.001-nit tolerance protects the 10-nit shadow
boundary from lookup roundoff.
Identity-size 4K reconstruction stays linear through expansion, normalized to
10000 nits. The selected Adaptive recipe uses an FP16 reconstruction intermediate
and FP32 expansion calculations. This removes the intermediate PQ encode/decode pair.
Explicit intermediate luminance prevents SDR inference. A bound rejection alone
re-encodes the unexpanded image. PQ recovery and protected-shadow re-encoding
are qualified within one logical 12-bit code, not byte-for-byte PQ identity.
The identity-size 4K path also prepares exact RGB8 transport bytes alongside
expansion. GUI is composed after content statistics. Resolve copies these bytes
and patches only metadata-covered rows; it does not re-read the full FP32 image.
Late GUI changes and guarded identity output retain ordinary composition/packing.
Full-raster transport comparison covers metadata repetition, ordinary chroma
LSBs, both orientations, SDR/PQ GUI and partial alpha.
GUI and subtitles are composed after analysis and use existing full-raster L5
visibility signaling. Unresolved Adaptive HDR Mapping frames accept updated GUI descriptors
without restarting content analysis. Visibility changes refresh the outgoing L5
candidate, including source-bound identity output.

The GPU uses compact reductions, bounded reconstruction/output resources and
asynchronous completion. Both RGB and packed preparation may return Pending. No image buffer
is downloaded to the CPU. This numerical qualification does not establish TV
appearance, Dolby equivalence or Intel/AMD hardware throughput.

## HDR10 to Dolby Vision: AI-assisted

This path estimates L1/L3 from HDR10 images. It does not recover original
authored DV metadata or invent creative CM2.9/CM4 trims.

### Analysis and model

GPU analysis emits 35 global and 38 spatial descriptors plus a 24 x 24 x 3
motion thumbnail. Compact descriptors feed a 222-feature calibrated vector.
A single versioned bundle contains normalization data and six LightGBM output
heads. Reference and Adaptive HDR Mapping share this bundle.

```text
feature_normalized[i] = (feature[i] - mean[i]) / scale[i]
residual[j] = model_head[j](feature_normalized) * bundle_strength
L1_candidate[i] = round_even(base[i] + residual[i]*4095)
L3_candidate[i] = round_even(2048 +
    (base[i]/4095 + residual[i+3] - L1[i]/4095)*2048)
```

Model and baseline arrays use **min, average, max** order; public L1 structures
use named fields. The fitted model's projection bounds are L1 min 0..12,
max 2081..4095, and average 819..max-1. Maximum also covers the measured peak.
L3 words are bounded to 0..4095. These are this model's research constraints,
not general DV parser rules. Strength and normalization belong to the pinned
model contract, not a user brightness slider.

The temporal path uses one second of lookahead. Scene cuts use motion and shape
changes while rejecting simple exposure changes, with confirmation over at
least 0.2 seconds. Seeks, discontinuities and policy changes reset the relevant
identity/window. Native LightGBM inference uses one CPU thread; decoded images
remain on the GPU and no Python runtime is used during playback.

Future candidate cuts stop the current scene's statistical window before
confirmation. The model's calibration prefix retains the confirmed-cut rule.
Simple exposure changes retain their measured peaks and are not scene cuts.

### Reference output

HDR10 pixels retain their source color interpretation without an enhancement
grade. Conversion and quantization into the DV transport still occur; source
storage is not promised bit-identical. Generated L1/L3 and active-area metadata
accompany the frame. This is an AI-assisted DV representation of HDR10, not a
recovered studio DV grade or an established improvement on every display.

### Adaptive HDR Mapping output

HDR10 AI Adaptive HDR Mapping shares the authored-DV pixel expansion, dense LMS/PQ output
analysis and temporal transaction. Input guidance uses the reconstructed L1
with signed-normalized L3 applied once. It supplies no creative anchors:
retention is one and trim-derived color severity is zero. L2/L8 trims are not
invented or applied. The model, feature extraction and calibration are unchanged.

Source reference M is the valid HDR10 mastering maximum, not MaxCLL or the
configured display reference T. Unknown mastering remains unknown, using a
conservative 10000-nit internal envelope. RC3 uses the same scene-guided exponent,
normalization, highlight expansion and midtone term described for DV above, with
retention one and color severity zero. `T<=M` does not by itself disable expansion
when scene highlights have headroom below `T`.

The 257 knots are linearly interpolated per pixel, with the same common-channel
shoulder and temporal limit. Luminance at or below 10 nits stays protected.
Equal effective scene guidance gives the same curve as DV without trims; this
does not mean AI recovers an authored Dolby Vision grade.

HDR10 uses the Reference path's native BT.2020 PQ conversion, without synthetic
Dolby reshaping or the former spline/display-mapping pass. The shared executor
uses FP32 pixel calculations, without an additional UNORM image. Capable GPUs
fuse conversion, expansion, all-pixel statistics and RGB8 transport. Four-pixel
statistic records quantize PQ to 16 bits; native-recovery and GUI PQ caches may
use half-float. The directly packed movie does not pass through those caches.
Movie-only direct output retains native recovery but omits the expanded GUI
cache. Metadata insertion then updates only covered transport rows in place.
Transformed output is analyzed before overlays;
L1 transformed through the scene curve and fresh L5 replace input L3. Identity retains the original AI image/metadata
pair. A source-bound rejection applies to the whole frame, not individual
pixels. Final display mapping remains TV-Led.

### HDR10+ Dolby Vision Rendering

The selected picture supplies an immutable, validated single-window HDR10+
snapshot. Its maximum MaxSCL channel is normalized linear light, with 1 equal
to 10000 nits. Convert that value through ST.2084 and quantize to 12-bit L1 max.
Targeted-system-display luminance is not a source peak.

HDR10+ AverageMaxRGB is not mean PQ. Valid percentiles estimate mean PQ by
weighted PQ trapezoids adapted from AVDVPlus HistogramPlus. Linear AverageMaxRGB
validates distribution consistency; the full distribution is not assumed known.
Missing/unusable percentiles retain supplied AI estimates, with signed L3 folded
once; otherwise PQ(AverageMaxRGB) is a labelled estimate. Minimum defaults to zero
without analysis. Output L3 is neutral. Zero MaxSCL requires a supplied AI estimate;
it is not reported as source-translated.

Authored Bezier curves and saturation mappings remain untranslated; no extra
pixel pass is added. Multi-window, invalid or mismatched source snapshots are
rejected without reusing an earlier RPU. This mode does not reconstruct a studio
Dolby Vision grade. The existing HDR10 Reference movie path and model are reused.

## Source map

| Implementation | Responsibility |
| --- | --- |
| `src/dvbridge_placebo.c` and dependency patches | Source representation and reconstruction |
| `src/dvbridge_creative.c` | Metadata resolution, CM controls and bounded Adaptive HDR Mapping fit |
| `src/cb1_dv_enhanced.c` and `src/cb1_dv_enhanced_shader.h` | Shared pixel expansion, curve/colour guidance, temporal state and authored scene-L1 transform |
| `src/dvbridge_render.c` | Rendering graph, creative hooks and DV/HDR10 output preparation |
| `src/dvbridge_core.c` | Metadata serialization and transport transaction |
| `src/cb1_hdr10_*.c` | GPU descriptors and temporal HDR10 analysis |
| `src/cb1_l1l3_model.c` | Native model inference and bounded L1/L3 projection |
| `src/cb1_hdr10plus_dovi.c` | Descriptive HDR10+ source peak and explicit estimate provenance |
| `src/cb1_circuit.c` | Engine and circuit identities |

[Creative-source attribution](CREATIVE-MAPPING.md) and
[licensing](LICENSING.md) identify the retained public references and notices.
