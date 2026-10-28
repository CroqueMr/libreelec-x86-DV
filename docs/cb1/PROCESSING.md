# Processing and metadata

CB1 reconstructs source images, applies the selected processing mode and prepares
output metadata. Kodi retains decoding, audio, subtitles and playback timing.

Native HDR10/HLG/SDR and [stereoscopic 3D](3D.md) remain outside CB1 conversion.
See [hardware support](HARDWARE.md) for supported integrated and dedicated GPUs.

## Standard and Master Reference

Both modes reconstruct the Dolby Vision source, including the applicable matched
FEL, and send TV-Led Dolby Vision with the source display-management metadata.

| Mode | Reconstruction | TV profile |
| --- | --- | --- |
| Dolby Vision Standard | Fixed performance-oriented reconstruction and input-chroma interpolation | Not required |
| Dolby Vision Master Reference | Exact source-domain reference arithmetic and dedicated FEL filters | Not required |

Standard accepts very small image differences for substantially higher rendering
performance. Master Reference aims for bit-perfect playback within its admitted
source/output contract. It does not establish equality to a certified player's
physical HDMI output. Resizing is a spatial operation, not an identity transform.

Master Reference has its own format checks. Global profile support does not mean
every profile is accepted by every rendering mode. Unsupported Master inputs use
the existing output-selection fallback; they are not silently reconstructed by
the reference algorithm.

The source-tree focus is [Master Reference](../../CB1/docs/MASTER-REFERENCE.md).
Expert settings select YCbCr or IPT-PQc2 Master output. This changes the payload
inside the RGB8 Dolby Vision tunnel, not the HDMI container. Profile 5 uses the
shared direct IPT path in both Master variants.

## Metadata use

| Metadata | Standard / Master | HDR10 Basic | HDR10 Expert | Adaptive |
| --- | --- | --- | --- | --- |
| RPU mapping / residual | Reconstruct source | Reconstruct source | Reconstruct source | Reconstruct source |
| L1 scene min/max/average | Forward to TV | Scene guidance | Scene guidance | Expansion strength and output scene descriptors |
| L3 offsets | Forward to TV | No Expert trim pass | Apply once with valid L1 | Apply once before curve construction |
| L2 CM2.9 trims | Forward to TV | Not applied | Compatible creative controls | Guide added light and color restraint |
| L5 active area | Preserve picture/borders | Preserve picture/borders | Preserve picture/borders | Exclude borders from expansion/analysis |
| L6 mastering / light levels | Forward when applicable | Source reference / HDR10 signaling | Static fallback / signaling | Source descriptors |
| L8 CM4 trims | Forward to TV | Not applied | Compatible HDR controls | Target responses and color restraint |
| L9 / L10 | Forward when applicable | No creative anchor selection | Resolve gamut / target anchors | Resolve compatible creative anchors |

Visible menus and subtitles use full-raster output L5 signaling so the TV does
not hide them in the black bars. This does not expand the source picture.

## Units

L1 values are **12-bit PQ codes, not nits**. With `E` as inverse ST 2084:

```text
scene luminance = E(L1_code / 4095)
```

`M` is the source mastering/reference maximum. `T` is the configured display
peak. Neither is a direct measurement of the current scene or the physical TV.

## Dolby Vision to HDR10 Basic

Basic uses source mastering information and valid scene statistics. It reconstructs
the Dolby Vision image, applies scene-guided spline tone mapping and perceptual
gamut mapping, then encodes BT.2020/PQ HDR10.

- No manual TV profile and no invented display peak.
- No L2/L8 creative trim pass.
- No inverse tone mapping to force dim scenes to the mastering maximum.
- Missing scene statistics use valid static source descriptors.

Dynamic Dolby Vision metadata cannot be transported as dynamic metadata in a
standard HDR10 signal. Its contribution must be reflected in pixels before output.

## Dolby Vision to HDR10 Expert

Expert maps to `T` and the configured gamut. P3-D65 is the default. Disable the
TV's dynamic tone mapping for this mode to avoid a second dynamic mapper.

Effective scene statistics include L3 once:

```text
effective_L1 = round(L1 + (L3 - 2048) * 4095 / 2048)
```

Compatible creative anchors are selected in their target domain and interpolated
by PQ distance. L2 and L8 are not stacked as two separate creative grades.

| Controls | Expert processing |
| --- | --- |
| Slope / offset / power | Decode and apply compatible primary controls |
| Chroma / saturation | Apply the compatible HDR color operation |
| CM4 midtone / clipping | Apply the decoded luminance controls |
| CM4 six-color saturation / hue | Preserve but do not execute SDR-only commands in HDR10 Expert |
| Spatial detail | Use the existing detail path when peak compression is active |

Missing or unusable L1 uses valid static source descriptors without leaving
Expert or retaining the previous scene's statistics. Unknown extra L8 targets
do not discard other usable anchors. Corrupt or contradictory metadata remains
guarded.

The creative output performs tone mapping once. Final gamut conversion and PQ
encoding do not add another scene tone map. BT.2020 out-of-volume colors are
limited even when no creative anchor is available. A higher configured peak does
not by itself multiply the whole film to that brightness.

## Adaptive HDR Mapping from Dolby Vision

Adaptive transforms reconstructed linear BT.2020 pixels, then updates scene
metadata to describe the transformed image. It is not a metadata-only filter.
The TV still performs its final Dolby Vision display mapping.

### Source guidance

- L1/L3 provide effective scene brightness.
- Compatible L8 anchors take precedence over L2; up to two anchors bracket the
  display reference using PQ-distance weights.
- Trim responses are evaluated in their own target domain, rather than applying
  the creative grade twice.
- With usable L1 but no creative trims, neutral trim guidance permits expansion.
  No L2/L8 creative controls are fabricated.
- Missing usable scene analysis or failed source-bound validation retains the
  original image/metadata pair.

### Expansion

For a scene peak `high`, average `mid` and smoothstep `H`, the curve builds 257
knots. Trim retention `r` is bounded to `[0.5, 1.15]`; absent trims use `r=1`.

```text
S = H(100, 400, high) * (1 - 0.5*H(0.04, 0.30, mid/max(high, epsilon)))
exponent = 2 + 2*H(0.04, 0.30, mid/max(high, epsilon))
reference = min(M, max(100, high))
```

The integrated retention curve is normalized at `reference`. When the TV has
headroom above that scene reference, highlights receive additional light.
A bounded midtone term can add up to the profile's `0.12*(M-10)` scale, weighted
by scene strength, trim retention and a smooth midtone window. This is a curve
coefficient, not a fixed 12% increase to every pixel.

Color-control magnitudes restrain added light rather than applying another
saturation/hue grade. A common RGB gain preserves linear chromaticity. A soft
shoulder limits added light to available channel headroom without reducing
source values already above the display target.

Pixels at or below **10 nits**, and pixels outside L5, bypass expansion. Dark
scenes are not automatically forced to fill the TV's range.

### Output metadata and stability

Effective authored L1 passes through the applied neutral-axis curve. Output L3
is neutral after folding; compatible source trims remain present. The declared
envelope covers the original source and transformed output.

Frame extrema validate the output but do not replace authored L1 every frame.
Curve/color changes share a time-based budget, advanced only by matching
presented pictures. This limits brightness pumping; seeks and mode changes reset
the temporal state. GUI and subtitles are composed after content analysis.

The current display path uses FP16 intermediates where selected by this Adaptive
policy. It is separate from Master Reference's exact reconstruction contract.

## HDR10 to Dolby Vision AI

One bundled **CB1-L1L3 0.1 LightGBM model** serves Reference and Adaptive AI.
GPU analysis builds luminance, color, spatial and temporal descriptors. A
normalized 222-feature vector produces L1/L3 estimates; output projection keeps
the predictions ordered and covers the measured peak.

Inference uses one CPU thread, without Python during playback. Lookahead and
scene handling associate predictions with their corresponding pictures. Seeks
and mode changes invalidate old predictions.

### Reference AI

Reference adds no enhancement grade. It converts the HDR10 source into the
Dolby Vision transport and sends estimated L1/L3 with the corresponding image.
It does not recover the studio's original RPU, generate authored L2/L8 trims or
guarantee a visual improvement over HDR10 on every display. Transport conversion
is not a promise of bit-identical HDR10 storage.

### Adaptive AI

AI L1/L3 guide the shared expansion executor. There are no authored L2/L8
anchors, so retention is neutral and trim-derived color restraint is absent.
The currently wired AI policy uses a cubic curve without the authored-DV
midtone term:

```text
extra(u) = S * max(T-M, 0) * u^3
```

The GPU interpolates the curve's 257 knots. Shadows at or below 10 nits stay
protected; `T<=M` selects identity. Output L1 is measured after processing and
L3 is not applied twice. A missing mastering maximum uses a conservative
internal bound, not a fabricated mastering claim.

Reference AI and Adaptive AI therefore share the model, but do not apply the
same pixel treatment. No claim of equivalence to authored Dolby Vision is made.

## Performance controls and output

Each circuit owns its input-chroma recipe. Async prepares at most one future
picture without changing native Kodi/fallback playback scheduling.
Master uses dedicated FEL filters; other applicable modes retain VAAPI/Nearest
selection. [Settings](PLAYBACK.md).

Dolby Vision uses an RGB8 byte tunnel carrying higher-precision video and
metadata, not ordinary 8-bit SDR. HDR10 conversion requires a driver-validated
10-bit-or-higher output. [Hardware](HARDWARE.md).

Full source equations and execution details are in
[CB1 algorithms](../../CB1/docs/ALGORITHMS.md).
