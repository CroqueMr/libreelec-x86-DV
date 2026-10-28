# Vega M HDMI Dolby Vision support

Targets: Radeon RX Vega M GL/GH in Kaby Lake-G systems, including i7-8705G and
i7-8809G. Their AMD display block is **DCE11.22**, not DCN. Hades Canyon HDMI
outputs are driven by the Radeon, not Intel HD 630.

## Changes

- Admit DCE11.22 through the existing AMD DV connector/EDID/atomic validation.
- Keep Polaris DCE11.2, other DCE families and existing DCN admission unchanged.
- Expose guarded HDR conversion independently of the DV switch. Retain native
  30-bit buffering and post-validation checks of actual link precision.
- Use the native DCE112/DCE110 AVI/VSIF packet programming.
- For DV transport only, bypass input prescale and any legacy LUT, use a
  24-bit RGB linebuffer and retain the existing degamma/regamma, CSC, dithering
  and full-range output guards. Ordinary playback restores its native settings.

No CB1 reconstruction, filters, metadata or rendering algorithms change.
The existing Generic firmware packaging already includes Vega M firmware.
No cross-GPU copy from the Intel GPU is added.

## Verification

Four host tests exercise the actual patched C functions: family/property
admission, input colour programming and linebuffer selection, including
ordinary/DCN controls. The initial admission/colour tests fail on original
behaviour; linebuffer testing requires the new selector. A separate regression
test checks independent HDR admission without weakening the DV byte path.
All four modified C translation units compile with the Linux 7.2.6 SDK.
Replaying the patch series on the pinned Linux archive reproduces all five
modified files exactly.

## Output requirements

Dolby Vision V1/V2, HDR10/HLG and HDR10+ are supported through the DCE11.22
driver path. The selected native HDMI route, display capabilities, bandwidth
and atomic validation must accept the output. [Driver/output matrix](DRIVER-COVERAGE.md).

Patch: `projects/Generic/patches/linux/linux-9925-vegam-dv-transport.patch`.
Included in R1.0.0 RC1 with Linux 7.2.6. NVIDIA Pascal support is included in the
same Generic image through its matched R580 stack.
