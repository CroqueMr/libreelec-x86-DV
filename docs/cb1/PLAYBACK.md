# Playback

Controls are in **Kodi > Settings > Player > Videos**. Output selection and
Player information are available at Basic level. Method, preset and manual
display profile appear at Advanced level when applicable.

| Mode | Result |
| --- | --- |
| DV Standard (TV-Led) | Reconstructed source video and frame-matched metadata; TV display mapping |
| DV Enhanced - Natural | Highlight-weighted treatment of existing metadata; source pixels preserved |
| DV Enhanced - Signature | Broader bounded treatment of existing metadata; source pixels preserved |
| DV Disabled (native Kodi) | Native Kodi playback and HDR handling |
| HDR10 Reference Basic | Source-derived HDR10 conversion; no manual TV profile |
| HDR10 Reference Expert | Creative metadata processing with a manual HDR10 display reference |

HDR10 sources offer native HDR10 and, when compiled and available, AI-assisted
Reference or Enhanced DV. SDR/HLG retain native playback. The selector does not
offer source-incompatible circuits.

The quick selector header shows `Source: Dolby Vision` or `Source: HDR10`.
DV modes precede HDR10 modes. HDR10 sources offer `DV Reference (AI)`,
`DV Enhanced (AI) - Natural`, `DV Enhanced (AI) - Signature` and `HDR10 Native`.
Unavailable output remains disabled with its reason. SDR/HLG have no custom
conversion selector.

All source-compatible choices are visible in a two-column grid. Configure the
TV profile in **Player > Videos**, not in the playback selector.

Enhanced uses a treatment reference of at least 1000 nits without changing the
stored TV profile. Natural is restrained; Signature uses stronger bounded
treatment. Unsupported metadata is preserved. L1-only sources retain the
existing fallback rather than synthesizing missing creative controls.

For Expert HDR10, disable TV dynamic tone mapping to avoid an additional mapping
stage. TV-Led DV still uses the TV's display mapper. Output mode changes are
committed at an accepted presentation boundary.

## Player information

With the enhanced panel enabled, **O** cycles:

1. Player information.
2. Playback mode selection, when applicable.
3. Video only, without panel sampling.

Play/pause and playback controls remain available. Disabling the enhanced panel
restores Kodi's stock information panel and disables the mode selector.

GPU render usage is this Kodi process's render-engine occupancy, including the
visible interface. It is not whole-GPU load or hardware decoder usage. Source
audio format is separate from decoded PCM/passthrough output.

Automatic playback diagnostics are stored in `kodi.log`. No upload is performed.
