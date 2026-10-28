# DV and HDR10+ driver coverage

## Scope

Execute the user's 2026-10-28 approval of the hardware audit, then repair AMD
DV EDID V1 compatibility. Preserve the frozen RC1 at
`94b5aa40639af9d46c45aa0c96708d56a4c37009` and its delivered images.
Work on `candidate/rc1-hardware-coverage`; no publication or mini-PC change.

## Approach

Reuse PRs #40 (Pascal), #43 (Vega M), #44 (Kaby Lake), #57 (Arc firmware).
HDR10+ PRs #45/#46 already exist in the candidate and must not be duplicated.
Use the existing shared DRM metadata transaction and native packet writers.
Do not add another video engine, shader or per-model Kodi backend.

Pascal keeps a matched opt-in R580 stack, never mixed with R615 components.
Default R615 stays intact. A user question on separate-image versus boot-time
selection is pending; implementation of the existing opt-in is independent.

## Requirements

- Cover native HDR10+ and DV-to-HDR10+ only, not HDR10+-to-DV.
- HDR10+ admission requires the actual selected driver/connector, sink version,
  PQ/BT.2020 and at least 10-bit output, with packet ownership tied to the frame.
- Preserve HDR10 fallback and ordinary Kodi state on rejection, stop and hotplug.
- Do not advertise a capability merely because an EDID or GPU name exists.
- Preserve Standard/Master movie pixels, filters, metadata and current V2 DV
  packet bytes. Only transport support/admission/packaging is in scope.
- Keep unsupported Intel/DCE hardware safely unavailable unless an actual
  native deep-output route is demonstrated; document physical limits honestly.
- Native HDR10+ V0/V1 and generated output must use a receiver-compatible
  version and valid payload semantics, not a version-bit-only rewrite.
- Vega M keeps DV-only RGB8 bypass isolated from ordinary/DCN colour handling.
- AMD V1 requires appropriate legacy/modern VSIF selected from parsed EDID;
  do not merely delete both V2-only guards. Reject LLDV-only/malformed EDID.
- Preserve the original AMD rejection reason where stream creation currently
  turns unsupported DV into a generic ENOMEM.
- No logs per frame, vendor-binary modification, polling packet writer or new
  unbounded queue. Source/licence receipts must match the chosen driver stack.

## Validation

RED/GREEN executable tests for missing firmware, new family admission, packet
bytes/checksum, >=10-bit enforcement, frame ownership, receiver versions,
V1/V2/DV-disabled/ordinary controls, failure and restoration. Compile affected
native translation units and run the full matched integration suite. Astra
reviews the full hardware implementation before the AMD V1 lot and validates
the final V1/V2 changes. Available test GPUs are not substitutes for absent
Pascal, Vega M, Arc or HDR10+ display hardware.

## Non-goals

No rendering-algorithm change, Adaptive rev B, scaler replacement, CPU frequency
forcing, release upload, forced HDMI selection or claim of physical validation
on unavailable hardware.
