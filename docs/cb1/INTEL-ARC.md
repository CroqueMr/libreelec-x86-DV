# Intel Arc dedicated GPUs

| Family | Kernel driver | Decode / processing | Dolby Vision output |
| --- | --- | --- | --- |
| Arc A-series / Alchemist DG2 | i915 by default; xe remains opt-in on this kernel | Existing iHD VAAPI / Mesa iris | Supported |
| Arc B-series / Battlemage | xe | Existing iHD VAAPI / Mesa iris | Existing native-HDMI path, supported |
| Iris Xe MAX / DG1 | i915 | Existing iHD VAAPI / Mesa iris | Supported through i915 and an admitted native-HDMI route |

## Change

`packages/linux/package.mk` now includes `xe/` alongside `i915/` in the x86
built-in firmware staging. The pinned kernel requests `xe/bmg_guc_70.bin` and
`xe/bmg_huc.bin` for Battlemage. Previously neither the built-in list nor the
runtime firmware selection included this directory.

The existing kernel enables `CONFIG_DRM_I915`, `CONFIG_DRM_XE` and
`CONFIG_DRM_XE_DISPLAY`. Both drivers compile the same patched Intel display
code, including the default-on Dolby Vision parameter and HDMI property.
Intel media-driver 26.3.5 already includes DG1, DG2 and Battlemage support.
No GPU-ID allowlist, force-probe override or rendering change is added.

## Limits

Dolby Vision still requires the existing native-HDMI checks, a compatible sink
and a successful atomic validation. DisplayPort outputs, adapters and HDMI
ports behind active DP converters are not enabled by this change. Decoding and
HDR10 processing remain available where the normal driver supports them.
Performance depends on the GPU, source and selected rendering mode.

## Verification

The firmware regression test executes the production x86 staging block and
checks that both Intel firmware namespaces, Battlemage binaries and symlink
targets reach the built-in firmware list. No mini-PC or Arc hardware is used.

## Sources

- [Pinned Intel media-driver support](https://github.com/intel/media-driver/tree/intel-media-26.3.5#supported-platforms)
- [Shared i915/xe display driver](https://docs.kernel.org/gpu/xe/)
- [Linux xe firmware selection](https://github.com/torvalds/linux/blob/v7.2/drivers/gpu/drm/xe/xe_uc_fw.c)
