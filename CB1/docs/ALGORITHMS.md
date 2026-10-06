# Algorithms and metadata

This reference describes **CB1 0.1** and the circuits listed in
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
| `M` | Source mastering peak, not measured scene maximum |
| `S` | Scene-dependent strength multiplier |
| `Y` | Luminance in the current working gamut |
| `w` | Bounded interpolation weight between compatible anchors |
| `clamp(x)` | Clamp to the interval 0 to 1 |
| `H(x)` | Smoothstep polynomial `x*x*(3 - 2*x)` after clamping |

ST 2084 uses `m1=2610/16384`, `m2=2523/32`, `c1=3424/4096`,
`c2=2413/128`, `c3=2392/128`:

```text
p = (L / 10000)^m1
P(L) = ((c1 + c2*p) / (1 + c3*p))^m2
metadata code = round(4095 * P(L))
```

Runtime float arithmetic and final integer quantization are separate stages.
libplacebo's linear working unit is 203 nits; this is a unit conversion, not a
display peak or an output brightness cap.

## Metadata use

| Metadata | Standard DV | HDR10 conversion | Authored-DV Enhanced |
| --- | --- | --- | --- |
| RPU reconstruction data | Reconstruct and transport | Reconstruct before conversion | Same reconstruction as Standard |
| L1 min/max/average | Transport | Maximum/average guide scene mapping; minimum validated and retained | Retained; scene ratio guides trim adjustment |
| L3 offsets | Transport | Expert applies to effective L1 once | Retained; effective L1 guides the scene ratio |
| L2 CM2.9 trims | Transport | Expert applies eligible controls | Fit only existing primary controls |
| L5 active area | Transport and mask borders | Preserve active-area geometry | Unchanged |
| L6 HDR mastering | Transport | Basic reference and static HDR descriptors | Unchanged |
| L8 CM4 trims | Transport | Expert uses the independent CM4 operator | Fit only existing primary controls |
| L9 mastering primaries | Transport | Expert resolves source mastering gamut | Unchanged |
| L10 target descriptions | Transport | Resolve compatible custom CM4 anchors | Retained; used to resolve existing controls |

Raw and parsed CM4 fields must agree. Optional-field presence follows the raw
block length, not whether the value is nonzero. Unknown targets are not assigned
invented peak, black-level or transfer values. Duplicate or inconsistent data
is not presented as valid processing.

L1-only authored DV does not acquire fabricated L2/L8 trims. Its Enhanced
treatment can therefore remain unchanged. Missing optional creative metadata
does not imply that source reconstruction is missing.

## Standard Dolby Vision

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

## Dolby Vision to HDR10: Reference Basic

Basic reconstructs the source, then uses libplacebo's spline tone mapper and
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

## Dolby Vision to HDR10: Reference Expert

Expert uses the manual display reference `T` and gamut, selected from BT.709,
P3-D65 or BT.2020. Reconstruction precedes target mapping and creative controls.
The working-domain hook owns tone mapping; later stages perform gamut conversion
and PQ encoding, not a second scene tone map.

Effective L1 values are `L1 + (L3 - 2048)` where L3 is present. Ordering and
range are checked before use. Maximum and average guide mapping; minimum is
validated and retained, not substituted for measured display black.

### CM2.9

Compatible trim anchors are selected around the display reference. Between
anchors, interpolation uses PQ distance rather than linear-nit distance:

```text
w = clamp((P(T) - P(Tlow)) / (P(Thigh) - P(Tlow)))
control = low + w * (high - low)
```

With no upper authored anchor, the CM2.9 resolver can use a neutral mastering
anchor. With no usable trim anchor, Expert retains its non-creative mapping.

For primary control words `c0..c4`:

```text
slope = c0/4096 + 0.5
offset = c1/4096 - 0.5
power = c2/4096 + 0.5
chroma = c3/4096 - 0.5
gain = c4/4096 - 0.5
v[i] = T * clamp(input[i]/T * slope + offset)^power
Y = 0.22897*v[R] + 0.69174*v[G] + 0.07929*v[B]
output[i] = v[i] * ((1+chroma)*v[i]/Y)^gain
```

The color step is skipped for zero luminance/components or neutral gain. Word
2048 is neutral. CM2.9 spatial `ms_weight` is preserved, not claimed as applied.

### CM4

The independent `cb1-cm4-v1` operator resolves L8 against preset or custom L10
targets. Only compatible gamut/transfer anchors participate. Gamut matching uses
the producer's signed 16-bit coordinate precision. Known incompatible transfers
are excluded; a custom L10 transfer remains explicitly unknown.

Decoded coefficients, rather than encoded words, are interpolated with `w`.
Absent controls stay neutral; absent target black levels stay absent.

| Control | Decode |
| --- | --- |
| Slope / offset / power | Same primary decoding as CM2.9 |
| Chroma base | `2^((c3-2048)/4096)` |
| Saturation gain | `2^((c4-2048)/4096)` |
| Spatial detail weight | `0.30*(c5-2048)/2048` |
| Midtone exponent `m` | `2^((mid-2048)/2048)` |
| Highlight clip strength `k` | `0.25*(clip-2048)/2048` |
| Six-color saturation | `2^((sat[i]-128)/256)` |
| Six-color rotation | `(pi/12)*(hue[i]-128)/128` radians |

After the primary SOP operation, with `x=clamp(Y/T)`:

```text
midtone Y' = T * x^m / (x^m + (1-x)^m)
clip Y' = T * clamp(x + k*x*H((x-0.5)/0.5))
```

RGB scales by `Y'/Y` while preserving exact neutral gray. Color controls operate
in IPT/PQ using libplacebo's gamut matrices. With normalized intensity `z`, the
primary chroma multiplier is `saturation_gain * chroma_base^(2*z-1)`.
Six-color controls use smooth hue weights
`exp(4*(cos(hue-center[i])-1))`, normalized to sum to one. Saturation blends in
log space; rotation blends in angle space.

Spatial detail uses the native libplacebo base/detail path only when the input
peak exceeds the output reference and the weight is nonzero. Otherwise it is
retained but not reported as applied. L2 compatibility and L8 are never stacked
as two creative passes.

## Authored DV Enhanced: Natural and Signature

The `cb1-dve-v3` policy keeps Standard-equivalent reconstructed pixels. It fits
the five existing L2/L8 primary controls to a bounded objective. L1/L3,
mastering descriptors, target descriptions and secondary controls remain intact.

### Reference and scene strength

```text
R = max(1000, T)
h = clamp((round(4095*P(R)) - master_q) / max(master_q, 0.000001), -0.5, 0.5)
r = E(effective_L1_average/4095) / E(effective_L1_maximum/4095)
S = 1 - 0.5*H((r-0.1)/0.4)
```

Here the three-argument clamp has explicit bounds. Missing L1 uses `S=1`;
zero L1 maximum uses `S=0`. `r` is a source-descriptor ratio, not measured FALL.
The 1000-nit floor applies to the treatment reference, not the saved TV profile
or source mastering metadata.

For the unedited authored luminance response `v` at an anchor peak `A`:

```text
x = clamp(v/A)
black_gate = H(v)                       // transition from 0 to 1 nit
highlight_gate = H((x-0.25)/0.75)
Natural gain = S * black_gate * 0.04 * max(0,h) * highlight_gate
Signature gain = S * black_gate * 0.04
goal = v + gain * max(0,v) * (1-x)
```

An additional channel-headroom factor prevents the luminance goal from pushing
the largest RGB component beyond the anchor peak. The goal's chroma multiplier
is `2^(S*C*clamp(1-maxRGB/A)/4096)`, with `C=32*max(0,h)` for Natural and
`C=64` for Signature.

Natural protects low/mid tones and expands eligible highlights; it can remain
neutral at a matching or lower reference. Signature permits a stronger bounded
midtone and color response. These objectives do not guarantee physical panel
brightness or expand every scene to `T`.

### Fit and preservation

A deterministic two-pass coordinate search adjusts five control words using
steps 256 down to 1. Each word remains within 0..4095 and within 512 codes of
its source. Validation checks grayscale monotonicity, near-black behavior,
authored plateaus, normalized PQ error, chroma and hue. The fit bounds are
`2/1024` PQ error, 2% relative chroma error and 0.5 degrees hue error.

All eligible L2/L8 edits commit together. An unresolved or rejected edit keeps
the complete source metadata family, not a partial modification. Missing trims
are not synthesized. This path needs no GPU image-analysis pass; the TV still
performs the final DV display mapping.

## HDR10 to Dolby Vision: AI-assisted

This path estimates L1/L3 from HDR10 images. It does not recover original
authored DV metadata or invent creative CM2.9/CM4 trims.

### Analysis and model

GPU analysis emits 35 global and 38 spatial descriptors plus a 24 x 24 x 3
motion thumbnail. Compact descriptors feed a 222-feature calibrated vector.
A single versioned bundle contains normalization data and six LightGBM output
heads. Reference, Natural and Signature share this bundle.

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

### Reference output

HDR10 pixels retain their source color interpretation. Generated L1/L3 and
active-area metadata accompany the frame in the DV transport. This is an
AI-assisted DV representation of HDR10, not a recovered studio DV grade.

### Enhanced output

Enhanced first maps pixels to the manual reference and gamut using the spline
and perceptual policy above. It then applies a selective linear-light operation.
For RGB normalized to `T`, let `a=min(RGB)`, `b=max(RGB)`:

```text
shadow = smoothstep(0.01, 0.02, b)
onset = smoothstep(start, end, b)
b' = b + brightness*S*shadow*onset*b*(1-b)
RGB' = RGB * b'/b
```

| Preset | Onset | Brightness coefficient | Chroma coefficient |
| --- | --- | --- | --- |
| Natural | 0.25 to 0.75 | 0.20 | 0.04 |
| Signature | 0.02 to 0.25 | 0.35 | 0.08 |

`S` uses the same smooth scene-ratio definition. Out-of-cube colors contract
around a common neutral value instead of independent channel clipping. Chroma
expansion is bounded by the RGB cube:

```text
g = (min(RGB') + max(RGB'))/2
c = (max(RGB') - min(RGB'))/2
room = min(g, 1-g)
t = min(1, c/room)
factor = min(1 + chroma*shadow*S*4*t*(1-t), room/c)
RGB'' = g + factor*(RGB' - g)
```

Zero/neutral cases bypass unsafe division. The result returns to BT.2020/PQ.
L1 is then measured from the processed output; source-estimated L3 is not
reused on deliberately changed pixels. The TV remains responsible for final
TV-Led display mapping.

## Source map

| Implementation | Responsibility |
| --- | --- |
| `src/dvbridge_placebo.c` and dependency patches | Source representation and reconstruction |
| `src/dvbridge_creative.c` | Metadata resolution, CM controls and bounded Enhanced fit |
| `src/dvbridge_render.c` | Rendering graph, creative hooks and DV/HDR10 output preparation |
| `src/dvbridge_core.c` | Metadata serialization and transport transaction |
| `src/cb1_hdr10_*.c` | GPU descriptors and temporal HDR10 analysis |
| `src/cb1_l1l3_model.c` | Native model inference and bounded L1/L3 projection |
| `src/cb1_circuit.c` | Engine and circuit identities |

[Creative-source attribution](CREATIVE-MAPPING.md) and
[licensing](LICENSING.md) identify the retained public references and notices.
