# R1.0.0-RC3 Preview

**Update 2 | 2026-11-02 13:19 CET (Paris)**

### Update 2 changes

- Smaller text throughout Player information.
- Simplified metadata blocks: Source blocks and Sent to TV or Used by CB1.
- Fixed text instead of scrolling values, with shorter descriptions and multiline diagnostics.
- Video processing is unchanged.

> **Work-in-progress build:** this preview evolves as fixes are added. Code cleanup is not complete. This is not a stabilized release.

## Changes since R1.0.0-RC2

### Dolby Vision

- Added GPU bilinear FEL upscaling, replacing the nearest-neighbor fallback when VAAPI scaling is unavailable.
- Added the Reference GPU FEL filter as a selectable option for other conversion modes. Master Reference retains its reference filter.

### Playback and stability

- Fixed cases where stopping playback during a resolution change could leave HDR signaling active instead of returning to SDR.
- Fixed stale HDR10 session reuse after a rejected output activation, ensuring subsequent playback prepares the required output surface.

### Settings

- Separate remembered rendering preferences for Dolby Vision, HDR10 and HDR10+ inputs.
- Automatic fallback no longer replaces the preferred rendering mode.
- Fixed rendering options incorrectly remaining unavailable after stopping a different source format.

### HDR10+

- Fixed source-specific preference selection during continued HDR10+ playback, preventing accidental use of the plain-HDR10 preference.

### Player information

- Corrected misleading "Unused blocks" reporting: metadata forwarded to the TV is no longer marked unused.
- Displays whether CM2.9-to-CM4 conversion is actually active, including live updates for Auto and Auto 2.

### Blu-ray menus

- Updated BD-J Java add-on packaging with matching libbluray 1.5.0 support files.
- Prevented stale or incomplete Java support files from being packaged. Requires the updated JRE add-on attached to this release.

### Diagnostics

- Added targeted diagnostics for deferred playback shutdown and SDR output restoration.

## Work in progress

- Improve HDR10 reliability.
- Fix support issues on some Intel Arc GPUs.
- Fix support issues on NVIDIA GTX 10-series and some RTX 50-series GPUs.
