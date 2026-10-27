# Adaptive rev B: signed-guide qualification

Offline replacement of the first rev B prototype. Algorithm:
`cb1-dve-signed-revb-v2`. No runtime engine, Kodi, shader, AI, mini-PC,
TV or published image changed. RC1 V1 remains frozen.

## Metadata-driven behavior

- L1 with L3 folded once establishes scene range and tonal balance.
- Selected L2 or L8 tonal controls are evaluated against neutral controls
  in the same authored target domain. The existing distinct CM2.9/CM4
  operators are reused; this is an independent CB1 model, not Dolby's mapper.
- The signed response shapes the highlight curve. Its signed mean controls
  amplitude separately, so normalization cannot erase a constant trim.
- HDR chroma/saturation signs constrain global expansion amplitude without
  applying a second color grade. This is not a complete chroma-selective
  interpretation of those trims; RGB direction is preserved instead.
- Authority decreases outside the authored target range. A 600-nit trim is
  not inverted or interpreted as an authored 2500-nit grade.
- Six-vector SDR controls and spatial tone detail are excluded from the
  expansion command. No image histogram, occupancy estimate or local mask.

The signed guide is clamped to +/-1 stop. Shape derivative multiplier is
`2^(0.75 * guide)`; amplitude is `clamp(0.85 + 0.30 * signed_mean, 0.55, 1)`.
The mean samples the uniform tonal domain, not the film's pixel distribution.
Each anchor has authority `weight * min(authored_peak / TV_peak,
TV_peak / authored_peak)`. These are explicit prototype policy choices.
The existing upper-range selector, <=10-nit protection, RGB component ceiling
and temporal slew remain. No complete trim is applied both locally and on TV.

Dolby documents distinguish CM2.9 curve controls from CM4 controls, and limit
six-vector secondaries to SDR. [Trim controls](https://professionalsupport.dolby.com/s/article/The-Dolby-Vision-Trim-Controls).
Metadata levels and target/source information are described in
[Metadata levels](https://professionalsupport.dolby.com/s/article/Dolby-Vision-Metadata-Levels).
These sources do not validate CB1's independent equations or upmapping policy.

## Render qualification

Neutral synthetic scene: L1 max 400 nits, L1 average 10 nits, 1000-nit
master envelope, 2500-nit TV, no trims. Calculated signal, not panel luminance:

| Input | Current Adaptive | Previous rev B | Signed rev B |
|---:|---:|---:|---:|
| 5 nits | 5 | 5 | 5 |
| 10 nits | 10 | 10 | 10 |
| 50 nits | 72.17 | 50.01 | 50.01 |
| 100 nits | 212.05 | 117.01 | 114.46 |
| 200 nits | 699.22 | 602.33 | 541.98 |
| 400 nits | 2393.83 | 2393.83 | 2181.08 |

The neutral amplitude leaves room for positive/negative trim guidance rather
than sending every scene maximum to the same near-peak destination.

Controlled scene with L1 max 800 / average 30 nits and a matching authored
2500-nit target, evaluated at an 800-nit input:

| Slope word | CM2.9 output | CM4 output |
|---:|---:|---:|
| 1536 | 2145.39 nits | 2145.39 nits |
| 2048, neutral | 2243.47 nits | 2243.47 nits |
| 2560 | 2329.99 nits | 2329.99 nits |

Opposite signs remain distinguishable after shape normalization. Power,
offset, mid-contrast and clipping-control sweeps are recorded separately in
the raw summary. CM2.9 does not acquire CM4-only mid-contrast/clipping controls.
These are responses of the local model, not a certification of Dolby trim feel.

GPU versus scalar reference: maximum 0.0354 code on a 12-bit PQ scale across
both variants/paths, 0.0287 for signed rev B. Protected GPU pixels are identical
between variants; linear/PQ storage roundtrip error is at most 0.000341 nit on
the synthetic test. Maximum signed rev B RGB component-ratio error is 0.000038.

Real single-layer probes: six independent frames per film and mode; four
sampled scanlines, 34,560 RGB components per film/mode. Avatar approximately
39-44 s uses one L2 target; Dragon approximately 1-6 s uses one L8 target.

| Film | Maximum change vs current Adaptive, PQ code12 | Mean absolute change | Protected roundtrip max |
|---|---:|---:|---:|
| Avatar | 239.31 | 100.88 | 0.000378 nit |
| Dragon, 3840x2020 | 56.83 | 11.27 | 0.000339 nit |

These intentional differences may be visible. They are not Delta E, YCbCr
chroma error or evidence of subjective superiority. No TV comparison was
performed. Real-film probes reject FEL input rather than silently omit EL;
FEL transfer is exercised by the separate synthetic renderer regression.

## Metadata and temporal checks

- Source bytes and policy unchanged; output identity matches the exact picture.
- Original L2/L8 and unchanged blocks preserved by index, not only by level.
- Output L3 neutral after input L3 integration; output L1 matches the actual
  plan's neutral-axis projection. No invented/refitted creative trims.
- P5/FEL transfer regressions pass with the substituted builder; existing
  analytic/table carrier bounds and metadata equivalence checks remain.
- 240-frame controlled sequences per variant: maximum adjacent change at a
  200-nit sample is 2 PQ codes for current Adaptive, 1 for signed rev B.
  Explicit cut/reset excluded; the existing per-knot slew bound passes.
- Dark-scene transitions remain independent of SDR-secondary values.

Remaining approximation: output L1 average is a neutral-axis projection,
not a new image/shot analysis. Against the synthetic arithmetic
`PQ(max(LMS))` proxy, the output-average residual is about -70.94 code12
for signed rev B, versus -79.85 for current Adaptive. This proxy is not
Dolby's editorial analysis. Preserving original trims does not prove they
remain optimal for the expanded pixels. No correction is hidden in output
metadata. Sparse film frames and bounded slew do not establish absence of
pumping on a real TV.

## Cost on the local development GPU

WSL Mesa D3D12 `AMD Radeon(TM) Graphics`, not either mini-PC. 3840x2160
expansion + statistics + fused carrier prepack + auxiliary PQ write;
RGBA32F input/auxiliary, RGBA8 carrier. Excludes decode, DV reconstruction,
final resolve/copy and HDMI. GPU queries, disjoint=0; three idle process runs,
72 post-warmup samples per variant/PQ path, alternating AB/BA order.

| PQ path | Current Adaptive median | Signed rev B median | Current p95 | Signed rev B p95 | Paired median / p95 delta |
|---|---:|---:|---:|---:|---:|
| Tables | 29.36 ms | 24.27 ms | 30.67 ms | 24.85 ms | -5.11 / -4.63 ms |
| Analytic | 20.85 ms | 22.88 ms | 23.29 ms | 25.16 ms | +2.03 / +2.83 ms |

This misses the prior +0.5-ms p95 additional-cost objective on the analytic
path. No new shader/pass does not imply equal GPU time. Removing per-pixel
color restraint and changing the curve also changes execution behavior;
the timing alone does not identify an instruction-level cause. No mini-PC
FPS, drop or headroom claim follows from these results.

CPU plan-only medians, excluding metadata resolution and submission:

| Input guidance | Current Adaptive | Signed rev B |
|---|---:|---:|
| L1 only | 4.29 us | 11.56 us |
| One L2 target | 19.06 us | 30.34 us |
| One L8 target | 12.97 us | 19.47 us |

## Verification and disposition

Full engine suite: 242 registered checks, zero failures, 15 unsupported skips,
117.37 s. Native integration suite: 212/212 passed, 205.49 s. Prototype-local
checks include opposite signs, constant-gain retention, target attenuation,
missing controls, invalid weights, L1-only operation, protected lows, neutral
ramp monotonicity, color ratios, ceiling, source immutability and temporal slew.
Existing dependency deprecation warnings persist in the test harness.

No runtime diff under `CB1/src`, `packages` or `projects` against the V1
checkpoint. The prototype is linked only into test executables. No image built
or deployed. Keep this as the replacement offline rev B, not a production
activation: analytic GPU overhead, L1-average approximation and real-TV
appearance remain unvalidated gates.

Raw evidence: `/home/dvbuild/adaptive-revb-20261027/signed` in local WSL
`DVBuild`. Earlier evidence remains in the parent directory. Summary:
[signed qualification data](adaptive-rev-b-signed-20261027.json).

Reproduce with the existing matched-dependency build:

```sh
ctest --test-dir /home/dvbuild/adaptive-revb-20261027/build -R adaptive_rev_b --output-on-failure
GALLIUM_DRIVER=d3d12 LIBGL_ALWAYS_SOFTWARE=0 EGL_PLATFORM=x11 \
  /home/dvbuild/adaptive-revb-20261027/build/tests/adaptive_rev_b_gpu --bench
python3 CB1/tests/reference/qualify_adaptive_rev_b.py /home/dvbuild/adaptive-revb-20261027/signed
```
