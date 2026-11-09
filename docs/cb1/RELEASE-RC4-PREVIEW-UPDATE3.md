# R1.0.0 RC4 Preview - Update 3

Work-in-progress preview.

- **HDR10/HDR10+ to SDR** and **Dolby Vision to SDR**, including complete applicable FEL reconstruction.
- **Independent SDR targets**: Reference, Bright room and Custom / Projector. HDR calibration remains separate.
- **HLG to Dolby Vision Reference**, alongside native Kodi HLG, with independently saved preferences. No HLG Adaptive mode.
- **Revised Player information**, based on [CorentinB's PR92](https://github.com/CroqueMr/libreelec-x86-DV/pull/92): Input / Processing / Output columns, applied metadata only, consistent level order and static single-line values with full details on demand.

The normal Generic image retains the [Update 2](RELEASE-RC4-PREVIEW-UPDATE2.md)
Blu-ray menus, Xe3 backports, installer USB logs, CEC and display controls.
NVIDIA support retains credit to [Hades / hadesdevls](https://github.com/hadesdevls/LibreELEC-Hades).
No Support image is built.

[Playback settings](PLAYBACK.md), [processing](PROCESSING.md),
[Player information](KODI-INFORMATION.md) and the [SDR/HLG engine contract](../../CB1/docs/SDR-HLG.md)
describe targets, consumed metadata and behavior on unsupported output paths.

Existing desktop GTX 10-series startup, Surface display switching, Xonar STX II,
affected Xe3 hardware and individual BD-J/CEC compatibility investigations remain
open. This update does not claim fixes for those hardware reports.
