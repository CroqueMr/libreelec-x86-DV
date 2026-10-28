# Intel Kaby Lake support

Targets: Intel Core 7th generation with HD 610/615/620/630 or Iris Plus 640/650.
Kaby Lake-G Radeon outputs are covered by a separate Vega M port.

## Supported path

- i915 DV admission already accepts Display 9, which includes Kaby Lake.
- Intel media-driver **26.3.5** includes Kaby Lake and HEVC Main10 support.
  `GEN9` and `GEN9_KBL` default to ON; both are ON in the inspected build cache.
- Generic OpenGLES already includes `iris`, `i915`, VAAPI and media-driver.
- Native HDMI, compatible DV EDID, RGB8 and neutral colour-state checks remain
  required. Existing DP/LSPCON refusals are unchanged.

No new kernel allowlist or rendering patch is needed for this software path.
The existing driver-policy test compiles the shipped policy and checks Display
9/10/11 admission, native HDMI rejection cases and untouched ordinary playback.

## Limits

Dolby Vision requires the admitted native-HDMI route. Systems routed through
DisplayPort adapters or an LSPCON do not gain support from their CPU model.
Display9 does not provide the native HDMI static-HDR path used for HDR10, HLG
or HDR10+ output. HDMI bandwidth and playback performance depend on the machine.
[Driver/output matrix](DRIVER-COVERAGE.md).

References:

- [Intel media-driver 26.3.5](https://github.com/intel/media-driver/releases/tag/intel-media-26.3.5)
- `packages/multimedia/media-driver/package.mk`
- `projects/Generic/patches/linux/linux-9910-common-dv-policy.patch`
- `tests/cb1/test_driver_policy.py`
