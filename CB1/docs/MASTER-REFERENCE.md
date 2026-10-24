# Dolby Vision Master Reference

Circuit: `CB1-DVDVMR.0.5`. Engine: `CB1 0.3`.

Opt-in integer reconstruction for source-domain Dolby Vision output.
Standard playback and the existing conversion circuits are unchanged.

## Admitted output

- Sources up to 3840x2160, including 1080p and cropped movies, fitted into a
  qualified 3840x2160 Dolby Vision HDMI carrier.
- PQ YCC or Profile 5 IPT-PQ-C2, 12-bit reconstruction and exactly representable source colour matrices
  accepted by the existing source-domain transport.
- Decoded 8/10-bit BL and, when required, frame-matched raw 8/10-bit EL.
- NV12, P010 or planar 10-bit 4:2:0 storage, with left or top-left chroma.
- Residual reconstruction accepts matching left/left or top-left/top-left BL/EL
  grids. Mixed cross-layer phases remain rejected.
- ESSL 3.10 or desktop GLSL 4.00 and renderable FP32 component planes.
- Default spatial filters and a single mapping partition.

HLG, custom filters, invalid geometry, other chroma positions
and unsafe arithmetic are not admitted. The existing output-selection fallback
applies. A rejected Master frame never silently uses Standard reconstruction.

Fast is effectively off. FEL uses `Reference GPU`, independently of the saved
VAAPI/Nearest preference. Preferences are retained for other circuits. No display
calibration is required.

Profile 5 retains its full-range IPT-PQ-C2 domain through integer RPU reshaping,
chroma resampling and RGB8 tunnel packing. Its original colour matrices,
offsets and creative metadata are transmitted for TV-Led processing. Movie
pixels do not undergo a YCbCr/RGB/LMS conversion or a PQ/linear round trip.
The diagnostic Master Reference IPT mode uses this same Profile 5 path.
GUI conversion is confined to the overlay footprint; the IPT black code is zero.

Standard always uses Fast, even when the global preference is Off. Master never
uses Fast, even when the preference is On. In Auto, sustained low presentation
headroom switches Master to Standard for the current playback and announces the
change only after successful Standard presentation. Preferences are not rewritten.

Canonical MEL has no active residual. Its unused EL filter flag does not require
an EL image or an EL spatial filter. Non-trivial NLQ still requires a matched EL.
For active FEL, the EL resampling flag selects half-size enlargement or same-size
bypass; inconsistent decoded dimensions are rejected.

## Reconstruction

The reference is ETSI GS CCM 001 V1.1.1, clauses 5.4.2 and 5.4.3, with the
deterministic filters from informative Annex B. Raw FFmpeg coefficients are
copied as integers, without a floating-point coefficient round trip.

1. Recover original component codes using unfiltered texture reads and storage
   bit shifts. Retain the decoded component grids.
2. Enlarge half-size EL vertically, then horizontally, using the Annex B luma
   and chroma filters, edge replication and each intermediate shift/clip.
3. Reconstruct luma on its original grid. For chroma MMR, reduce original BL
   luma before reshaping, not reshaped luma or an arbitrary interpolant.
4. Evaluate polynomial/MMR terms with Q20 intermediate truncation. Accumulate
   using two 32-bit words with checked signed 64-bit bounds.
5. Apply NLQ offset, signed dead-zone contribution and declared residual limit.
   Round and clip once at the reconstruction depth.
6. Resample reconstructed chroma to the declared 4:2:2 carrier, then reuse the
   existing metadata packets, parity and RGB8 packing.

For prediction `V`, residual `R` and reconstruction depth `D`:

```text
H = clip((V + R + 2^(15-D)) >> (16-D), 0, 2^D-1)
```

The scalar GPU primitive also qualifies 10-bit reconstruction. The HDMI adapter
currently admits only the 12-bit source-domain carrier above.

### Declared spatial conventions

MMR uses luma rows `2*y`, `2*y+1`. The printed equation's second `y+1` index is
interpreted as inconsistent with its half-height grid. This is an explicit
interpretation, not an official erratum.

For left chroma, output vertical enlargement uses the Annex B BL six-tap phases.
For top-left chroma, aligned rows copy and intervening rows use the Annex B
half-phase eight-tap coefficients vertically. Horizontal 4:2:2 samples remain
on their component grid. Output clips to the reconstructed code depth.
These are contract 1 output conventions, not a claim that Annex B specifies
the entire HDMI output chain.

The Annex B EL filters operate on the decoded component arrays for both admitted
matching phase pairs. No phase metadata is rewritten. Chroma output retains the
BL's signalled phase. MMR reduction retains the stated row-pair convention above;
this is a reproducible ETSI-based contract, not a certified-player comparison.

## Execution

EL packets enter the existing bounded queue and are decoded when pairing needs
them or at drain. An already buffered exact-PTS picture is returned before
submitting future packets. Decoder references, completion fences and queue limits
are unchanged.

Reconstruction stays on the GPU. Pooled FP32 planes retain exact integer results
for the separable EL filter, reconstructed chroma and output chroma. Luma
reconstruction is fused with final sampling. L5-masked rows omit reconstruction
while retaining the full chroma-filter halo. Identical
sampling bounds are shared by both chroma components. Identity polynomials and
range-proven 32-bit products avoid redundant wide arithmetic; 64-bit accumulation
and the general NLQ path remain available. All filter shifts and clips are
unchanged. Final sampling and carrier packing are fused. The existing shader cache,
frame leases, asynchronous handoff and presentation commit are retained. No
extra frame queue or CPU pixel processing is introduced.

Unscaled placement reconstructs and packs directly into the destination viewport.
A lightweight carrier initialization preserves metadata, borders and GUI outside
that viewport. No full-picture FP32 copy or spatial resampling is needed.

For resized geometry, reconstruction first runs on the original source grid into
the existing FP32 texture. Fit and paired chroma sampling retain FP32 precision
and the target orientation. Already reconstructed codes bypass ordinary colour
conversion. Resized outputs include spatial resampling and are not labelled
bit-identical to an unscaled source. The full-raster 4K reference path is unchanged.

For scaled Profile 5 on GPUs supporting fragment quad exchange, the final
FP32 scaling pass packs the carrier directly. Horizontal neighbours exchange
their filtered values without materializing another 4K FP32 image. The filter,
quantization and metadata are unchanged. Other profiles and unsupported GPUs
retain the materialized transport path.

The independent test-only integer oracle covers signed arithmetic, polynomial
pivots, MMR orders, NLQ and spatial filters. GPU tests compare logical codes and
complete carrier bytes. SDR/PQ overlay tests check the movie region outside the
declared footprint. Unsupported inputs fail explicitly.

Exactness is relative to this documented contract. It does not establish Dolby
certification or equality to a certified player's physical HDMI output.
Hardware throughput requires separate measurement.

The renderer selects exact paired-row reconstruction in the matched library.
Identity mappings without a residual can combine reconstruction, integer chroma
filtering and transport in one pass on GPUs supporting fragment quad operations.
Each aligned 2x2 fragment quad shares the overlapping integer chroma taps for
both row phases. Odd destination rows, other mappings and unsupported GPUs
retain the general integer path. Filters, rounding and outgoing metadata do not
change; no extra decode or presentation queue is introduced.
The fused UNORM unpack returns the same integer codes for every supported
8/16-bit storage word, including words with nonzero ignored low bits.
Identity taps accumulate before depth widening: the absolute eight-tap bound
is 6,334,416, below2^23. FP32 represents these integer sums exactly; the original
signed rounding is preserved by power-of-two division and floor.

Profile 5 remains in its decoded IPT-PQ-C2 domain through reconstruction and
transport. Master uses integer reconstruction and the exact chroma filter,
independently of the Fast preference. Standard may use FP32 reconstruction and
a compact five-tap chroma filter on supported left-sited 10-bit inputs. Its
mapped chroma grid uses RG UNORM16; metadata and tunnel packing are shared with
Master. Unsupported Standard inputs retain the existing YCbCr path. Other
profiles and conversion circuits do not select this Profile 5 strategy.
