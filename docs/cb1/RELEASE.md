# R1.0.0 Beta5 - Playback stability and wider format support

Changes from the MVC-corrected [Beta4](RELEASE-BETA4.md).

## Playback

- Improved scaling and placement for non-4K sources without a resolution-specific workaround.
- Improved Master Reference scheduling with visible panels and 10-bit/8-bit output transitions.
- Extended shared BL/EL assembly to declared dual-track MP4/MKV and dual-PID TS/M2TS sources.
- Corrected dual-layer seek invalidation and original packet-framing use during common-anchor probing.
- Aligned decoder surface allocation with existing FEL buffering.
- Improved audio recovery after temporary output loss.
- Corrected HDR state reporting after a rejected metadata request.
- Improved EDID extension handling and recovery of rendering-mode availability.

## Information and interface

- Enhanced Player information now uses shared Kodi resources and native fonts.
- Disabling it restores the active skin's native information dialog.
- Quick rendering selection preserves the active skin's native selector layout.
- Corrected parsed L3 and output-snapshot consistency for HDR10-to-Dolby Vision AI.
- Master Reference IPT is not part of the normal build.

## Known limitations

- HDR10 reports on some older Intel HDMI configurations remain under investigation.
- Heavy conversions and visible menus may exceed low-power GPU capacity.
- Adaptive HDR Mapping still requires visual qualification across more content.
- Dedicated NVIDIA GPUs remain experimental.

See [hardware](HARDWARE.md), [processing](PROCESSING.md) and [licensing/credits](LICENSING.md).
