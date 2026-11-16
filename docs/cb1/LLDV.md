# LLDV and HDR10 output

## Native low-latency Dolby Vision

**Purpose.** Render Dolby Vision on the PC for the exact target advertised in the display’s Dolby Vision EDID. Send the result as native low-latency Dolby Vision.

CB1 reconstructs the source from its base layer and RPU, including a matched enhancement layer for FEL. The player maps the reconstructed image to the target from the active display’s Dolby Vision EDID. That target supplies peak luminance, black floor and color primaries. The result is packed into a driver-admitted low-latency HDMI format with Dolby Vision signaling.

The circuit requires valid target data and a compatible output. RPU reconstruction and available creative controls are resolved before mapping and packing. Incomplete or invalid EDID data, incompatible targets and driver or timing limitations can make it unavailable. Player Information shows the target used for active playback. [Circuit version](../../CB1/docs/CIRCUITS.md) · [Rendering and metadata](PROCESSING.md) · [Rendering implementation](https://github.com/CroqueMr/libreelec-x86-DV/blob/91052933890da72d211373183aa1d1e398df75d9/CB1/src/dvbridge_render.c)

## HDMI format selection

The LLDV HDMI format selector appears under Dolby Vision default playback when LLDV is selected. It reports the display data and explains why unavailable formats cannot be selected. An accepted format depends on both the display’s advertised capabilities and the driver’s output checks at the selected timing. On the qualified AMD path, 4:2:2 has 10 useful bits in a 12-bit carrier. The selector labels forced formats experimental. See the [AMD and Intel format notes](PLAYBACK.md#dolby-vision-lldv-format-selection). [Native HDMI support](DRIVER-COVERAGE.md#circuit-mapping)

The RX550 Lexa (PCI ID 1002:699f) offers experimental 4:2:2 10-bit LLDV at native HDMI UHD 23.976 Hz only. Intel Display9–12, Arc B and Nova Lake on native HDMI use the same opt-in packed transport. The driver still validates the exact display mode and scanout before the picture is sent. These added routes need hardware qualification.

On NVIDIA R615, native 4:2:2 12-bit uses an integer RGB16 scanout and the NVKMS BT.2020 conversion. It requires an available UNORM16 GBM/EGL visual and a Dolby EDID that advertises 12-bit 4:2:2. Where the native surface is unavailable, the 12-bit option uses the experimental packed TMDS carrier with explicit selection. Native R615 HDMI output still needs receiver and capture validation.

Intel Display11 and later offer native RGB 10-bit on the admitted HDMI output when the Dolby block advertises 10-bit RGB/4:4:4 and the exact RGB 10-bit link and scanout qualify. AMD DCN2.0, DCN2.1 and the supported DCN3.x families share the native 4:2:2 10-bit output path. The Intel and AMD additions still need physical validation for the newly admitted combinations.

NVIDIA R580 offers native 4:2:2 10-bit when the GPU, HDMI port, EDID and RGB10 scanout qualify. Other supported R580 paths keep the explicit forced option. The NVIDIA routes confirm the accepted link state through NVKMS before reporting native LLDV playback.

Auto prefers native 10-bit routes before native 12-bit routes. Display Details also shows the RGB and YCbCr 4:4:4 depths the display advertises.

## HDR10 : LLDV Reference conversion

This separate circuit maps the reconstructed Dolby Vision image to manually configured peak luminance, black floor and gamut. The output is ordinary HDR10 with static HDR signaling and requires accepted output depth of at least 10 bits. [Tone mapping and creative controls](../../CB1/docs/ALGORITHMS.md#dolby-vision-to-lldv-reference--hdr10-output)
