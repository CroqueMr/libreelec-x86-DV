# R1.0.0 RC1.1 Debug

Changes since R1.0.0-RC1.1. Includes the RC1.1 HDR10+ decoding and incomplete Expert TV-profile routing fixes.

## Fixes

- Fixed Master startup readiness incorrectly reported as a rendering failure, for both YCbCr and IPT output.
- Keep rendering failure counters per file, including failed first-frame attempts.
- CB1 remains **0.4**. Film processing and Dolby Vision metadata are unchanged.

## Diagnostics

- Automatic, rate-limited Master readiness, failure-stage and counter-owner diagnostics.
- BL/EL plane dimensions and validated DMA import layout.
- Expert TV-profile requirements, native HDR10+ rejection fields and generated HDR10+ statistics/packet fingerprints.
- AMD driver capability-gate decisions retained from boot.

## Still under investigation

- RX7600 FEL vertical detail loss (#61).
- Native HDR10+ V1 sources rejected by representability checks (#62).
- Repeated generated HDR10+ packets on the reported test clip (#64).
- RX9070 XT native Dolby Vision availability (#66). DCN4 is not enabled by this build.

HDR10+ validation and supported driver families are unchanged. The Debug image was built and software-tested; affected RX7600/RX9070 XT hardware behavior is not claimed fixed.
