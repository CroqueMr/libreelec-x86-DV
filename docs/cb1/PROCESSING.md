# Processing and metadata

**CB1 0.1** reconstructs DV sources, processes the selected rendering mode and
prepares output metadata. Kodi handles decoding, audio and playback timing.

## Conversion paths

| Source and mode | Pixel processing | Metadata processing | Output |
| --- | --- | --- | --- |
| Dolby Vision: DV Standard (TV-Led) | RPU reconstruction and applicable matched FEL | Transport source display-management metadata | DV, TV-Led |
| Dolby Vision: DV Enhanced - Natural or Signature | Same reconstructed pixels as Standard | Fit existing L2/L8 primary controls | DV, TV-Led |
| Dolby Vision: HDR10 Reference Basic | Reconstruction, spline tone mapping and perceptual gamut mapping | L1 scene guidance and source mastering reference | HDR10 |
| Dolby Vision: HDR10 Reference Expert | Reconstruction, display-reference mapping and eligible creative controls | Effective L1/L3 and CM2.9/CM4 controls | HDR10 |
| HDR10: DV Reference (AI) | Preserve HDR10 source pixels | Estimate L1/L3 with LightGBM | DV, TV-Led |
| HDR10: DV Enhanced (AI) - Natural or Signature | Display-profile processing, Natural or Signature | AI scene guidance; measure L1 after processing | DV, TV-Led |

Native HDR10/HLG/SDR and disabled DV support retain Kodi's existing behavior.
No player-led/LLDV output is implemented. The TV performs final mapping for DV.

## Metadata and reconstruction

Profile 7 FEL reconstruction combines BL, RPU and the applicable matched EL
before output conversion. Missing or mismatched FEL is not reported as complete
BL-only reconstruction. Active-area borders follow L5 and output geometry.

| Field | Content | Use |
| --- | --- | --- |
| RPU mapping | Polynomial/MMR reshaping, transforms and residual parameters | Reconstruct source pixels before DV output or HDR10 conversion |
| L1 | Scene minimum, maximum and average PQ | Basic/Expert scene mapping; Enhanced scene-strength calculation |
| L3 | Offsets to L1 | Compute effective scene values once in Expert/Enhanced |
| L2 | CM2.9 creative trims and target peak | Expert applies eligible trims to pixels; DV Enhanced fits existing primary words |
| L5 | Left/right/top/bottom active-area offsets | Preserve active picture and signal-black borders |
| L6 | Mastering and content-light descriptors | Basic source reference and HDR10 static metadata |
| L8 | CM4 primary, midtone, clipping and six-color controls | Expert applies eligible fields; DV Enhanced edits only the five primary words |
| L9 | Source mastering primaries | Expert source-gamut interpretation |
| L10 | Custom CM4 target descriptors | Resolve compatible L8 target anchors |

PQ metadata codes use 0..4095. Peak mastering metadata is not measured scene
brightness. Gamut, target transfer and field presence are checked independently.
Absent creative blocks are not synthesized. Standard transports source controls
for the TV to apply; "forwarded" does not mean applied to pixels by CB1.

## Source reconstruction

BL is the base layer; EL is the enhancement layer. For FEL, the decoded EL is
paired to the BL picture by picture identity and presentation timestamp, then
used with the RPU residual parameters. Layer decode order may differ from
presentation order. MEL does not add a full residual.

Reshaping, residual reconstruction and source color transforms precede every
DV-derived rendering mode. HDR10 conversion does not discard an applicable FEL.

## DV to HDR10 Reference Basic

Basic uses a source-derived mastering reference and valid L1 scene information,
not a manual TV peak. It does not force dim scenes to fill the output range.
The pipeline is reconstruction, scene-guided spline tone mapping, perceptual
gamut mapping and BT.2020/PQ encoding. Valid L1 maximum/average guide the mapper;
otherwise it uses static source descriptors. Inverse tone mapping is off.
Basic does not apply L2/L8 creative trims or use the manual TV profile.

## DV to HDR10 Reference Expert

Expert uses the manual display peak `T` and gamut: BT.709, P3-D65 or BT.2020.
P3-D65 is the default. Disable the TV's dynamic tone mapping for this mode.

L3 modifies the scene descriptors once:

```text
effective L1[i] = L1[i] + L3[i] - 2048
```

Valid maximum/average guide tone mapping. Minimum is retained, not used as a
measured display black level. Creative anchors interpolate in PQ distance:

```text
w = clamp((PQ(reference) - PQ(lower)) / (PQ(upper) - PQ(lower)), 0, 1)
```

### CM2.9 controls

For encoded words `c0..c4`, neutral is 2048:

```text
slope = c0/4096 + 0.5
offset = c1/4096 - 0.5
power = c2/4096 + 0.5
chroma = c3/4096 - 0.5
gain = c4/4096 - 0.5
v[i] = T * clamp(input[i]/T * slope + offset, 0, 1)^power
Y = 0.22897*v[R] + 0.69174*v[G] + 0.07929*v[B]
output[i] = v[i] * ((1+chroma)*v[i]/Y)^gain
```

Zero luminance/components bypass unsafe division. With no usable creative
anchor, Expert still performs display-reference mapping. L2 spatial weight is
preserved, not applied.

### CM4 controls

L8 targets use their preset or corresponding L10 descriptor. Compatible
gamut/transfer anchors are selected; decoded coefficients are interpolated.
L2 compatibility and L8 are not stacked as two creative passes.

| Control | Calculation |
| --- | --- |
| Slope / offset / power | Primary decoding above |
| Chroma base | `2^((c3-2048)/4096)` |
| Saturation gain | `2^((c4-2048)/4096)` |
| Midtone exponent `m` | `2^((mid-2048)/2048)` |
| Highlight strength `k` | `0.25*(clip-2048)/2048` |
| Six-color saturation | `2^((sat[i]-128)/256)` |
| Six-color rotation | `(pi/12)*(hue[i]-128)/128` radians |
| Spatial detail | `0.30*(weight-2048)/2048`, active during peak compression |

After the primary operation, let `x = clamp(Y/T, 0, 1)`:

```text
midtone Y' = T * x^m / (x^m + (1-x)^m)
highlight Y' = T * clamp(x + k*x*H((x-0.5)/0.5), 0, 1)
```

`H` is clamped smoothstep: `H(x)=x*x*(3-2*x)`. RGB scales by `Y'/Y`.
Color controls use IPT/PQ, smooth six-hue weights and bounded chroma changes.
Absent fields stay neutral. Spatial detail uses libplacebo's native base/detail
path only when the input peak exceeds the display reference.

The creative output hook performs tone mapping once. The final stage performs
gamut conversion and PQ encoding, not a second scene tone map.

## DV Enhanced

Natural and Signature adjust existing creative metadata, not reconstructed
pixels. The treatment reference is `max(1000, manual peak)` without changing the
saved TV profile or source mastering peak.

Let `P` convert nits to normalized ST 2084 PQ and `E` convert normalized PQ to
nits. The treatment reference and headroom are:

```text
R = max(1000, manual peak)
h = clamp((round(4095*P(R)) - source_master_PQ) / source_master_PQ, -0.5, 0.5)
r = E(effective_L1_average/4095) / E(effective_L1_maximum/4095)
t = clamp((r-0.1)/0.4, 0, 1)
S = 1 - 0.5*t*t*(3-2*t)
```

`S` reduces treatment strength for scenes with a high average relative to their
maximum. Missing L1 uses `S=1`; zero maximum uses `S=0`.

For authored luminance `v` at an anchor peak `A`, define
`x=clamp(v/A,0,1)` and `B=H(clamp(v,0,1))`, a near-black gate from 0 to 1 nit:

| Calculation | Natural | Signature |
| --- | --- | --- |
| Luminance gain `g` | `S*B*0.04*max(0,h)*H((x-0.25)/0.75)` | `S*B*0.04` |
| Luminance goal | `v + g*max(0,v)*(1-x)` | Same formula |
| Chroma coefficient `C` | `32*max(0,h)` | `64` |
| Chroma multiplier | `2^(S*C*clamp(1-maxRGB/A,0,1)/4096)` | Same formula |
| Tonal range | Highlight-weighted; low/mid tones protected | Broader response above near-black |
| Reference at/below source mastering peak | Neutral goal | Bounded treatment remains possible |

Channel headroom limits the goal before fitting. These are fitting objectives,
not guaranteed percentage changes in the TV's physical luminance.

For example, a 4000-nit source with a 2000-nit manual peak gives no positive
Natural headroom. It is not stretched to fill the TV's range.

### Metadata fitting

Five words are fitted: slope, offset, power, chroma weight and saturation gain.
Two coordinate-search passes use steps from 256 down to 1. Each result stays in
0..4095 and within 512 codes of its original word. Validation limits are:

- PQ error: `2/1024`.
- Relative chroma error: `2%`.
- Hue error: `0.5` degrees.

Black/near-black, grayscale monotonicity and authored plateaus are protected.
L2/L8 edits commit together. A rejected fit or unresolved target preserves the
source family. Secondary controls, L1/L3, mastering and target descriptors are
unchanged. L1-only input receives no invented creative trims.

## HDR10 to Dolby Vision with AI

One LightGBM bundle serves Reference, Natural and Signature. GPU analysis builds
global/spatial luminance and color descriptors plus a motion thumbnail. The
model estimates L1/L3 from a normalized 222-feature vector:

```text
feature[i] = (descriptor[i] - mean[i]) / scale[i]
residual[j] = model_head[j](feature) * bundle_strength
L1[i] = round_even(baseline[i] + residual[i]*4095)
L3[i] = round_even(2048 +
    (baseline[i]/4095 + residual[i+3] - L1[i]/4095)*2048)
```

The model order is min/average/max. Projection enforces legal code bounds,
ordered L1 values and coverage of measured peaks. It does not generate authored
L2/L8 creative trims. One second of lookahead stabilizes scene handling; seeks
and mode changes invalidate old predictions. Native inference uses one CPU
thread, with no Python playback runtime.

### Reference

Source HDR10 pixels are preserved. Estimated L1/L3 travel with the corresponding
image in the DV output. These are image-derived estimates, not recovered studio
metadata.

### Enhanced Natural and Signature

Pixels are first mapped to the manual peak/gamut using spline tone mapping and
perceptual gamut mapping. For linear RGB normalized to the reference peak, with
`b=max(RGB)`:

```text
shadow = smoothstep(0.01, 0.02, b)
onset = smoothstep(start, end, b)
b' = b + brightness*S*shadow*onset*b*(1-b)
RGB' = RGB * b'/b
```

| Parameter | Natural | Signature |
| --- | --- | --- |
| Onset | 0.25 to 0.75 of reference peak | 0.02 to 0.25 |
| Brightness coefficient | 0.20 | 0.35 |
| Chroma coefficient | 0.04 | 0.08 |

`S` is the scene-strength calculation above. The RGB cube bounds chroma:

```text
g = (min(RGB') + max(RGB')) / 2
c = (max(RGB') - min(RGB')) / 2
room = min(g, 1-g)
t = min(1, c/room)
factor = min(1 + chroma*shadow*S*4*t*(1-t), room/c)
RGB'' = g + factor*(RGB' - g)
```

Zero cases bypass division. Out-of-range colors contract around neutral instead
of clipping each channel independently. The result returns to BT.2020/PQ.
Output L1 is measured after processing; source-estimated L3 is not reused on
changed pixels. Final DV mapping remains TV-Led.

## Output and integration

Standard DV uses an RGB8 byte tunnel carrying higher-precision image/metadata
information. It is not ordinary 8-bit SDR. HDR10 uses PQ output and an eligible
10-bit-or-higher scanout path. Mode availability follows the source, renderer
and active display capabilities; no unsupported signaling is forced.

## Implementation

| CB1 file | Processing |
| --- | --- |
| `src/dvbridge_placebo.c` | Source representation and reconstruction |
| `src/dvbridge_fel.c` | EL decode queue and exact picture pairing |
| `src/dvbridge_creative.c` | Metadata resolution, creative controls and Enhanced fit |
| `src/dvbridge_render.c` | Rendering graph, HDR10 mapping and AI output measurement |
| `src/dvbridge_core.c` | Metadata serialization and DV transport |
| `src/cb1_hdr10_*.c` | GPU descriptors and temporal analysis |
| `src/cb1_l1l3_model.c` | LightGBM inference and L1/L3 projection |

[Playback controls](PLAYBACK.md) and [build instructions](BUILD.md).
