# RC1 Preview2 feedback corrections

Start from the private RC1 Preview1 tag. Reproduce Beta5 reports before adding
targeted corrections. Preserve the frozen artifacts and do not publish.

## Chosen boundaries

- Ordinary SDR, HDR10 and HLG playback must use Kodi's native output lifecycle.
  An allocated or retired CB1 context is not evidence of an active output override.
  Genuine DV and HDR-conversion restoration must still complete safely.
- PGS subtitles and SDR controls must both remain visible in Master Reference.
  Reuse Kodi's compositor and existing overlay surfaces; do not enable a route
  that silently drops either layer or falls back from Master.
- Preserve film reconstruction, colour calculations, source metadata and native
  scaling filters. Preserve the existing GUI-related L5 policy.
- Reproduce each FEL container/seek report independently. Do not pair arbitrary
  HEVC tracks, invent timestamps, remove validation or force DV without evidence.
- No Adaptive algorithm, Bluetooth, display-selection or third-party skin changes.
- An unrepeatable report remains open; a neighbouring test is not its resolution.

## Approaches

For NVIDIA HLG/PVR the user explicitly chose vanilla behavior. Gate CB1's
transaction on real requested/active output ownership, not cached resources.
Disabling HEVC acceleration or changing the proprietary driver is excluded.

For mixed PGS/GUI, normalize the two GUI layers before the existing native overlay
handoff. A new engine compositor or forced packed admission without a complete
overlay would enlarge scope or omit content. Prototype the native merge first.

## Evidence gates

- Actual-method RED/GREEN witnesses for native-output isolation and mixed PGS/GUI.
- Native restoration, pending output, overlay orientation/alpha and repeated
  redraw checks. No accumulated GUI blending across retries or paused redraws.
- Real BL/EL packet witnesses for seek alignment, preserving decode order and
  requiring proven random-access anchors before discarding a prefix.
- Full integration suite, patch replay, source locks and targeted build checks.
  Separate software reproduction from physical NVIDIA/HDMI confirmation.

