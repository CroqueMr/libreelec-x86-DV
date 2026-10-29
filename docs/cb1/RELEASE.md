# R1.0.0 RC1.1 - HDR10+ and HDR10 Expert fixes

Changes since R1.0.0-RC1.

## Fixes

- Fixed an HDR10+ decoding metadata error that could incorrectly trigger HDR10 fallback.
- Fixed output selection when HDR10 Expert is selected without a complete TV profile, preventing incorrect HDR initialization.
- Updated CB1 to **0.4**.

## Diagnostics

- Added targeted, rate-limited logs identifying output preparation waits, missing TV configuration and FEL availability.
- Added display-profile values and BL/EL texture dimensions, layouts and chroma positioning to existing diagnostic reports.

## RX7600 issues awaiting confirmation

- **FEL vertical detail (#61):** reported loss of detail between adjacent rows remains unconfirmed. Software tests preserve BL row detail; additional diagnostics are included.
- **HDR10 Expert startup (#63):** the missing-TV-profile routing defect is corrected, but startup with a correctly configured profile still requires confirmation on the affected hardware.
