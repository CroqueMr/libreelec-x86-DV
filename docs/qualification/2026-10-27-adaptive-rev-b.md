# RC1 V2: Dolby Vision Adaptive HDR Mapping rev B

Status: offline prototype, not enabled in Kodi or a release image. Existing Adaptive remains unchanged.

## Scope

- RC1 V1 source checkpoint: `checkpoint/rc1-v1-20261027`, `5a457f67f97d5aa3e61ea8f93802e175c0f48d1c`.
- V2 branch: `candidate/rc1-v2-adaptive-revb`.
- Circuit: `Dolby Vision Adaptive HDR Mapping rev B`, algorithm `cb1-dve-selective-revb-v1`.
- The prototype is linked into qualification executables only. No runtime source, shader, Kodi patch, AI model or dependency changed.
- Existing compiled RC1 remains on `f5002ad86080082a4eb989729419dba389c682df`; its archive SHA-256 is unchanged: `73d8b825b87e5c69550ad834e946e7f3bf49cbadeac2693bf381014462429056`.
- No mini-PC access, TV operation, publication or new LibreELEC image build.

## Algorithm

Start from the existing authored-DV Adaptive plan, after effective L1/L3 and HDR trim resolution. Preserve the source metadata and transmitted trim blocks.

Remove only SDR-secondary hue/saturation influence from the HDR expansion command. Retain primary HDR guidance. Multiply added light by a smooth upper-range selector calculated on CPU:

```
high = PQ_decode(effective_L1_max)
mid  = PQ_decode(effective_L1_avg)
key  = smoothstep(0.04, 0.30, mid / high)
lo   = max(10, high * (0.12 + 0.08 * key))
hi   = max(lo + 1, high * (0.65 + 0.10 * key))
rev_B_extra(Y) = existing_extra(Y) * smoothstep(lo, hi, Y)
```

This tonal-balance heuristic is not a measurement of highlight occupancy. It cannot identify faces, snow or specular objects. Coefficients are prototype choices, not Dolby controls.

The existing shader, RGB common gain, component ceiling, protected lows, packet generation and temporal slew are reused. Output L1 still uses the current neutral-axis approximation; output L3 is neutral after its input influence has been folded once. No L1 correction, new histogram, second trim application or automatic output-trim refit is introduced.

## Pixel qualification

Analytical CPU example, neutral 400-nit scene high / 10-nit tonal reference, mastering envelope 1000 nits, configured TV peak 2500 nits:

| Input nits | Existing Adaptive | rev B |
|---:|---:|---:|
| 5 | 5 | 5 |
| 10 | 10 | 10 |
| 50 | 72.17 | 50.01 |
| 100 | 212.05 | 117.01 |
| 200 | 699.22 | 602.33 |
| 400 | 2393.83 | 2393.83 |

These are signal calculations, not measured panel luminance. Rev B reduces midtone expansion while retaining the upper highlight response. It does not promise to match a manual regrade.

Actual shader, neutral/color synthetic raster, both PQ implementations, local GPU:

- Maximum GPU versus scalar-prototype difference: 0.0354 code on a 12-bit PQ scale.
- Protected low-light output is bit-identical between existing Adaptive and rev B on the exercised pixels. CPU pixels at or below Y=10 nits are unchanged.
- Existing linear/PQ roundtrip error remains: up to 0.00035 nit on the synthetic low lights. This is not an expansion-induced black change.
- Maximum RGB component-ratio error against the input: 0.000045 in the exercised shader samples. Common gain preserves linear chromaticity mathematically; floating storage/encoding introduces small numerical differences.
- Neutral ramp monotonicity, no intended darkening, targets 600–4000 nits, no-trim operation, HDR-trim sensitivity and SDR-secondary independence passed.

Actual single-layer film probes use six decoded frames per mode and four sampled scanlines per frame, 34,560 compared RGB components per film:

| Clip | Largest rev B / Adaptive PQ-code difference | Mean absolute difference | Maximum protected roundtrip error |
|---|---:|---:|---:|
| Avatar, approximately 39–44 s of the stored excerpt | 228.96 | 96.12 | 0.000378 nit |
| Dragon, approximately 1–6 s, 3840×2020 source | 50.96 | 8.14 | 0.000339 nit |

Differences are RGB PQ signal codes, not YCbCr chroma error, Delta E or measured TV differences. The changes from existing Adaptive are intentional and can be visible. Sampled protected pixels are bit-identical between the two variants. These few frames do not establish subjective superiority or whole-film behavior. No real 1917 FEL image comparison was performed; decoded FEL omission is explicitly rejected by the film probe.

## Metadata qualification

- Input metadata immutable; every preserved L2/L8 and other unchanged block checked by its original index, including multiple targets of the same level.
- Output L1 equals the projection of the plan used for that exact picture/revision. Output L3 is neutralized once, not accumulated.
- Real Avatar/Dragon prepare/completion paths passed both variants. Source bounds, source envelope and output packet handling remain the existing mechanisms.
- Existing P5/FEL transfer test reused with rev B substituted: analytical/LUT output metadata remains exact between those implementations; the existing carrier-error thresholds pass.

Remaining approximation: even with input L1 average deliberately matched to an arithmetic `PQ(max(LMS))` test distribution, projected output average differs from that measured proxy by about -79.85 codes, for both variants. Rev B does not solve this residual. The proxy is not Dolby's editorial shot analysis, so this number is not a certified Dolby-analysis error. No estimate is written back as an automatic correction.

The returned maximum/mean statistics use different linear/PQ domains on different shader paths. They remain diagnostic/guard values, not interchangeable L1 replacements. Source/output metadata consistency does not guarantee identical displayed blacks after a proprietary TV mapping.

## Temporal qualification

Two 240-frame controlled CPU sequences at 60 Hz, independent histories, small alternating source-max changes and an explicit reset at frame 120:

| Variant | Maximum adjacent output change at a fixed 200-nit sample, excluding the explicit cut |
|---|---:|
| Existing Adaptive | 2 PQ codes / 12-bit |
| rev B | 1 PQ code / 12-bit |

The existing per-knot slew bound passed. These sequences qualify bounded response to this stimulus, not absence of all pumping on a TV. Film probes are sparse independent-frame comparisons, not a real-time temporal replay. No scene detector or delayed occupancy feedback was added.

## Cost

Backend: local Windows PC through WSL Mesa 25.2.8 D3D12, reported renderer `AMD Radeon(TM) Graphics`. This is **not** the LibreELEC AMD mini-PC or N100. GPU elapsed queries were available and disjoint=0. Software-renderer results are used for correctness only.

4K synthetic expansion + fused statistics kernel, excluding reconstruction, decoding, HDMI presentation and later packing. Three idle runs, 24 post-warmup samples per variant/path/run; variants alternate order. No pixel downloads inside timing. Absolute times are specific to this backend and workload.

| PQ path | Adaptive median | rev B median | Adaptive p95 | rev B p95 | Paired delta median / p95 |
|---|---:|---:|---:|---:|---:|
| Tables | 29.37 ms | 28.17 ms | 30.17 ms | 28.97 ms | -1.21 / -0.67 ms |
| Analytical | 20.85 ms | 22.73 ms | 21.88 ms | 24.12 ms | +1.88 / +2.51 ms |

The analytical path misses the +0.5 ms p95 additional-cost objective. No claim of zero drops, HDMI headroom or mini-PC speed follows from these measurements. No extra pass does not imply equal execution time: changed uniform data and branches can change shader cost. This observation is not yet a demonstrated instruction-level cause.

CPU L1-only plan construction: medians 4.52 microseconds existing / 4.99 microseconds rev B in the recorded run. This excludes decoder, full trim resolution and GPU submission.

Rejected experiment: retaining 1/64 of the attenuated gain below the selector did not remove the analytical-path overhead. Removed; no extra setting or dormant implementation retained. Initial timings collected concurrently with other qualification work are excluded from the retained timing results.

## Integration decision

Verification: full engine suite, 242 registered checks, zero failures and 15 unsupported/skipped; native Kodi integration suite, 212/212 passed. No rev B symbol is linked into the runtime engine archive. Source/image freeze receipt passed. Existing dependency deprecation warnings are unchanged; no new prototype compiler warning was observed.

Keep rev B as an offline alternative. Do not replace current Adaptive yet. Remaining gates are the analytical-path overhead, the neutral-axis L1 approximation and real-time/TV perceptual qualification under later explicit device authorization.

Raw summary: [adaptive-rev-b-20261027.json](adaptive-rev-b-20261027.json). Test and benchmark source is under `CB1/tests/`; the production engine is unchanged.
