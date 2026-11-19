# Adaptive rev B runtime test build

Install the qualified signed rev B on the N100 for visual comparison. Keep
current Adaptive and every other circuit unchanged; RC1 V1 artifacts stay frozen.
No publication. The known analytic GPU overhead is accepted for this test build,
not a claim of mini-PC performance or Dolby equivalence.

Promote the existing builder into CB1/src without changing its numerical code.
Use an explicit policy boolean, valid only on authored-DV Adaptive FP16. This
keeps all existing FP16/FEL/P5 optimizations without multiplying precision enums.
Reset temporal history when switching between Adaptive and rev B. HDR10 AI
policy always clears the flag; its ingress rejects a flagged policy.

Kodi adds output preference6 (existing0..5 unchanged), named Dolby Vision
Adaptive HDR Mapping rev B, plus policy telemetry code8 and a new circuit ID.
Reuse Adaptive capability/profile admission; expose it in settings, O menu,
Player information and existing bounded diagnostics. No skin code. Existing
settings/default modes are preserved. No automatic selection of rev B.

Build DV-R1.0.0-RC1-V2 locally with the complete current source (including
the approved SDR-return fixes). Reuse the existing build cache but do not
overwrite frozen RC1 artifacts. Verify package contents and checksums, then
use the native LibreELEC updater on the N100, keeping settings/videos and
a known-good rollback image. Confirm hardware identity before mutation.

Alternatives: replacing current Adaptive removes A/B comparison; compiling
test code by textual inclusion is not a clean engine integration. Neither is used.
