# Adaptive rev B: signed metadata guidance

Replace the offline rev B builder only. Runtime Adaptive, AI paths, RC1 V1,
mini-PCs and published artifacts remain unchanged. No image analysis.

Evaluate each selected L2/L8 tonal response against its neutral response in
the same authored target domain, using the existing CM2.9/CM4 operators.
Clamp signed log2 response ratios to [-1, 1]. Weight each anchor by its
resolver weight and min(authored peak / TV peak, TV peak / authored peak).
This attenuation is CB1 extrapolation policy, not an authored upmapping trim.

Build a positive cumulative highlight shape with derivative multiplier
2^(0.75 * signed guide). Normalize shape at the scene reference separately
from amplitude. Mean = sum(guide[1..192])/192, uniformly sampling the lower
75% of the tonal domain above 10 nits, not pixel occupancy. Excluding the
upper quarter reduces endpoint-clipping influence on amplitude; shape still
uses all 257 knots. Color = sum(authority * clamp(log2(chroma_base) +
log2(saturation_gain), -1, 1)). Amplitude = clamp(0.85 + 0.30 *
clamp(mean - 0.25 * color, -1, 1), 0.55, 1).
A constant signed response must survive normalization. Signed HDR
chroma/saturation controls constrain amplitude but are not executed as a
second color grade. Six-vector SDR controls and spatial detail
are excluded. L1/L3-derived tonal balance still delays expansion of mids.

Reuse existing pixel shader, black protection at <=10 nits, RGB-ray ceiling,
temporal slew and output metadata builder. Preserve original L2/L8 blocks;
neutral-axis L1 projection is approximate, not a new shot analysis or Dolby
certification. Do not invent or refit creative trims.

Qualification: signed +/- trims, constant gain, authored-domain attenuation,
L1-only, CM2.9/CM4, invalid anchors, monotonic neutral ramps, colors, ceiling,
dark transitions, metadata integrity; real sampled Avatar/Dragon frames;
three alternating local GPU runs and full engine/native regressions.
