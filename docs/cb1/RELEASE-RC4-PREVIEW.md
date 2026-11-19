# R1.0.0 RC4 Preview

Normal Generic x86_64 prerelease. Update 1 is published; see
[Update 2](RELEASE-RC4-PREVIEW-UPDATE2.md) for its successor and current validation.
The historical validation below retains its original image scope.

## Included changes

- Blu-ray ISO/menu fixes: visible-menu input ownership, safe BD-J dirty-rectangle copying, HTTP ISO menu roots, authored still handling, language-switch navigation marks and clip preroll. The player is corrected; source ISO files are not rewritten.
- Preserve disc-authored audio/subtitle selection while opening playback, and retire deselected internal subtitles before waiting for a sparse replacement track. Menu overlays remain separate from subtitles.
- Advertise the bundled Java stereo capability accurately so compatible discs can choose their authored HDMV fallback. Physical stereo and complete stereoscopic Java menus are not claimed validated.
- Retain the Intel HDMI60Hz link-capability correction and the startup hold until the requested display mode is committed.
- Integrate the HDR10+ curve-validation/frame-pacing work from [PR #91](https://github.com/CroqueMr/libreelec-x86-DV/pull/91), preserving accepted curve output and its validation threshold.
- Match the R580 driver source/userspace versions and initialize selected NVIDIA KMS before Kodi and the installer. R580 now retains fractional CTA/HDMI modes and offers their missing integer-rate twins, as R615 already does.
- Build EGL-GBM once from official 1.1.4 sources (ABI filename 1.1.3). The source package owns the common library/platform JSON; neither NVIDIA payload overwrites it. Include attributed hook bounds/null/error/lifetime fixes.
- Correct VAAPI depth selection when an inputstream hint says 8 bits but FFmpeg's decoded software format is 10 bits. Keep the existing fallback for absent software formats. This fixes a reproduced software defect relevant to [YouTube #89](https://github.com/CroqueMr/libreelec-x86-DV/issues/89); confirmation on the reported YouTube/DASH hardware path is still needed.

## Validation

- 475 host tests executed successfully, no skipped tests, with matched sources and both exact NVIDIA source archives.
- Native regression checks reproduce the VAAPI depth and R580 mode-list defects before correction and pass afterwards under ASan/UBSan. Eight EGL hook cases and both vendor installation recipes pass; source ownership is checked against the image.
- Full image construction succeeded. 224 Kodi, 27 R615, 25 R580, 2 EGL and 4 libbluray source owners match the inspected build; 130 staged CB1 copies are checked. Installed Kodi code/data and the common EGL library match their linked allocated sections, with only the expected Kodi RUNPATH normalization.
- The complete image booted on the Intel N100 test PC: Kodi Home and RPC were available at 3840x2160/60Hz, runtime/flash hashes matched, and original settings were retained. The original complete RC3 image and settings were restored afterwards. This was an integration boot check, not a complete playback qualification.
- The ISO campaign retained 24 independently reviewed representative disc qualifications and 2 tester acceptances. Historical checks keep their original image scope; this exact Preview is not an exhaustive replay of every menu/bonus/language combination. BD-Live and physical stereo remain unqualified.

## Reports still requiring affected-setup confirmation

- RTX4090/HDR10: the supplied photograph shows an NVIDIA flip timeout/warning followed by a Kodi segfault. The initiating cause is not established from that photograph; this draft does not declare that crash fixed.
- [Xe3/Wildcat Lake #93](https://github.com/CroqueMr/libreelec-x86-DV/issues/93): the image contains WCL kernel entries and PTL firmware, but the reported black boot still needs the device's PCI identity/boot evidence and an affected-machine test.
- N100 delayed start: repeated NAS-name lookup failures and a 26.461s pre-input delay need local/by-IP/by-name comparison. The supplied Sony sample is VP9 8-bit without detected Dolby Vision metadata.
- N150 freeze, separately reported in #93: the log shows repeated TrueHD passthrough sink/channel-open failures before video starvation. Audio capability/device confirmation is required; display-sync is not forced as a workaround.
- Additional RGB-range, HDMI recovery/deep-output and VSIF coexistence comparisons remain scoped follow-up work. No unverified GPU-wide recovery or copied GPLv3-only component is included.

## Files and sources

The draft provides the normal installation image, LibreELEC update archive,
corresponding-source archive, vendor-input archive and SHA256SUMS. Extract the
two source/input archives into the same parent directory to reconstruct the
source tree and its download cache. The source manifest identifies the exact
image inputs and any documentation/CI overlays in the publication snapshot.

The Support variant is excluded from this draft. Raw user logs, local test
captures, credentials and private build history are excluded from the exports.

Acknowledgements: the pacing contribution from lessbones, and the attributed
R580 integer-rate and EGL hook fixes from Hades, with source author headers
and applicable notices retained. See
[investigation scope](https://github.com/CroqueMr/libreelec-x86-DV/blob/R1.0.0-RC4-Preview/docs/cb1/RC4-PREVIEW-INVESTIGATION.md).
