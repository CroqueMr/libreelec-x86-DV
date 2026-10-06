# R1.0.0 Beta1

- Kodi 22 RC1 with CB1 0.1 integrated into the native player.
- Dolby Vision Standard and Enhanced, with Natural or Signature presets.
- Dolby Vision-to-HDR10 Basic and Expert conversion, including FEL reconstruction.
- HDR10-to-Dolby Vision AI conversion with the included LightGBM model.
- Player information and source-aware rendering selection, available with **O**.
- Expanded Intel driver families and experimental AMD iGPU support.

Settings: **Player > Videos**. Standard Dolby Vision is the default.

## Downloads

- `.img.gz`: clean installation on a USB drive or SSD.
- `.tar`: native LibreELEC update; copy to `/storage/.update/` and restart.
- Source archives: matching build sources, dependency downloads and license notices.
  Not needed for installation.

Source builders should extract both source archives into the same directory.
See [build instructions](BUILD.md).

Keep a backup before updating. Performance depends on hardware and content.

## Known issues

- Some frame drops with Profile 7 FEL on a small number of files on N100/N150.
- Newly enabled Intel families and AMD support require hardware testing.

Report issues with the CPU/GPU, display, connection chain, build version and
`kodi.log`.
