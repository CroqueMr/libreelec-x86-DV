# Vega M: experimental HDMI Dolby Vision

Targets: Radeon RX Vega M GL/GH in Kaby Lake-G systems, including i7-8705G and
i7-8809G. Their AMD display block is **DCE11.22**, not DCN. Hades Canyon HDMI
outputs are driven by the Radeon, not Intel HD 630.

## Changes

- Admit DCE11.22 through the existing AMD DV connector/EDID/atomic validation.
- Keep Polaris DCE11.2, other DCE families and existing DCN admission unchanged.
- Do not expose the private HDR10 deep-colour extension on Vega M.
- Use the native DCE112/DCE110 AVI/VSIF packet programming.
- For DV transport only, bypass input prescale and any legacy LUT, use a
  24-bit RGB linebuffer and retain the existing degamma/regamma, CSC, dithering
  and full-range output guards. Ordinary playback restores its native settings.

No CB1 reconstruction, filters, metadata or rendering algorithms change.
The existing Generic firmware packaging already includes Vega M firmware.
No cross-GPU copy from the Intel GPU is added.

## Software qualification

Four host tests exercise the actual patched C functions: family/property
admission, input colour programming and linebuffer selection, including
ordinary/DCN controls. The initial admission/colour tests fail on original
behaviour; linebuffer testing requires the new selector. A separate regression
test catches and excludes unintended HDR10 property exposure.
All four modified C translation units compile with the Linux 7.2.6 SDK.
Replaying the patch series on the pinned Linux archive reproduces all five
modified files exactly.

## Hardware qualification pending

This is not a verified bit-perfect HDMI claim. Final wire bytes, physical DV
activation, bandwidth, transitions, hotplug and VAAPI/FEL playback must be tested
on a Vega M system. No Vega M machine or mini-PC was accessed.

Patch: `projects/Generic/patches/linux/linux-9925-vegam-dv-transport.patch`.
Base: Beta5 normal `abde400bbf8ef754c971f437dc321bdd03a5986b`, Linux 7.2.6 with
its existing native DV patches. Physical Pascal support is a separate draft.
