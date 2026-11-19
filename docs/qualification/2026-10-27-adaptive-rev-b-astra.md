# Astra xhigh: Adaptive rev B challenge

Reviewed commit: `c82dfa63ac15ca412d512eff51ca814b38b584d7`, against RC1 V1 `5a457f67f97d5aa3e61ea8f93802e175c0f48d1c`. Read-only review, no device access.

## Verdict

Acceptable as an offline prototype after two targeted corrections. Not approved for production activation.

## Findings and resolution

1. SDR secondaries could survive an IDENTITY/DARK_SCENE return, then re-enter HDR guidance through the temporal fade from READY. Added a regression comparing two SDR-only variations through that transition. It failed on differing interpolated color arrays before the fix. The builder now clears secondary guidance on every valid plan, including IDENTITY; curves, colors and pixels match after the fix.
2. The timer also measured fused carrier prepack and auxiliary PQ output. Added recorded/asserted configuration fields to each measurement and corrected the summary/report. The evidence validator first failed on the old incomplete records. Three idle A/B runs were repeated with explicit flags; no-disjoint elapsed queries pass validation.

## Confirmed strengths

- No runtime source, shared shader, AI model or player patch changed.
- Small separate builder; no current-frame measurement feedback or extra GPU pass.
- Immutable source and trim-block preservation checked by index, including repeated metadata levels.
- Neutral-axis L1 approximation and its remaining residual are disclosed rather than labeled Dolby analysis.
- Raw timing summary was independently regenerated during review; A/B differences were consistent across the three original idle runs.

## Remaining limits

The local analytical path remains slower and misses the additional-cost target. Controlled temporal sequences are not whole-film anti-pumping qualification; film probes recreate the renderer per sample. No conclusion on TV appearance, Dolby-equivalent mapping, displayed blacks, real 1917 FEL frames, HDMI cadence or mini-PC performance is made. Those are outside this offline authorization.

Deferred minor: harden the evidence summarizer against mixed backend identities and duplicate pairs. Current retained records were inspected and independently summarized; this does not change the measured current result. Local reproduction/evidence locations are now in the main qualification report as part of the timing-method correction.
