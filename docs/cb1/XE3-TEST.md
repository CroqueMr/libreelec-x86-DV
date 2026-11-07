# Xe3 / Wildcat Lake display backports

Base: public RC4 Preview Update 1, commit `0766befdfedc548c6a19fa417fb338da5de5a2fc`.
Included in the general image `DV-R1.0.0-RC4-Preview-Update2`, alongside [installer boot logging](INSTALLER-LOGS-XONAR.md). Linux stays at 7.2.6.
The experimental player information panel from PR92 is excluded.

The FD80/FD81 Xe driver, Iris/Mesa, iHD/media-driver and embedded PTL/DMC
firmware already exist in the base image. This update adds display backports;
it does not add force_probe or claim that the HP Omnidesk boot issue is fixed.

## Backport order and dependencies

All ten patches are imported without source edits from Intel's upstream
repository, retaining authors, reviews, upstream commit IDs and links.

| Patch suffix | Upstream commit | Dependency / purpose |
| --- | --- | --- |
| 01 | 25ea7671bdbc | One scaler per WCL display pipe; display 30.02 support already exists. |
| 02 | b42b656db138 | Disable WCL pipe joining; existing DP joiner owner is preserved. |
| 02a | aa8faabadc59 | Define CD2X pipe-select register masks used by patch 03; preserve existing pipe encodings. |
| 03 | 67d77d9472c6 | Introduce explicit CD2X pipe-select mask helper for patch 04. |
| 04 | aad969968824 | Skip absent CD2X pipe-select fields on PTL+ during CDCLK probe. |
| 05 | 96cb6f956651 | Use existing forcewake accessors under GMBUS mutex; add posting-read accessor. |
| 06 | 39c2d49c9ece | Sample I2C pin state without changing direction; prerequisite of 09. |
| 07 | e860dbc18495 | Preserve firmware pullup bits on gen2/3; prerequisite of 09. |
| 08 | 548a600780cc | Keep PNV clock gating outside GPIO access; prerequisite of 09. |
| 09 | b21a0ab8fb95 | Preserve write-only masks and sibling GPIO state on every write. |

The optional GPIO debugfs control (last patch of the submitted series),
unrelated ICL clock encoding changes, and CDCLK diagnostic refactoring are
not dependencies and are excluded. The existing GMBUS hardware path remains
the first choice; the GPIO fallback is corrected without forcing its use.

## Verification and qualification

`tests/cb1/test_intel_xe3_backports.py` compiles the actual patched C owners
against CPU-only register and connector fixtures. It covers read-only GPIO
sampling, write-only mask handling, sibling pin state, older display versions,
WCL DP joiner rejection, eDP/MSO guards and valid BIOS CDCLK preservation.
The CD2X helper is also compiled with the actual register definitions to
catch missing header prerequisites and preserve BXT/ICL/TGL encodings.
The complete pinned Linux patch stack must replay with fuzz zero.

These checks do not validate electrical I2C timings or a real display link.
On the affected HP, test cold boot first and preserve the boot journal,
kernel log, PCI driver binding, connector status and EDID. Then test Kodi,
VAAPI decode, HDMI audio, SDR/HDR and Dolby Vision separately. Compare the
same cable, display mode and HDMI/DP route with the public RC4 image.
The N150 playback issue in issue 93 is a separate investigation.
