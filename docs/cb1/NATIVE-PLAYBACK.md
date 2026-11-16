# Native Kodi playback

Kodi owns decoding, audio, subtitles, playback timing and ordinary signal selection. The output driver checks the display and the negotiated link. The **Output** section of Player Information shows the accepted format. [Driver and HDMI output matrix](DRIVER-COVERAGE.md) · [Playback settings](PLAYBACK.md)

## Dolby Vision

**Purpose.** Let Kodi choose its ordinary output and fallback for the source profile.

**Kodi default** uses Kodi’s original route and fallback for the source profile. The available result follows the source representation, decoder, display and driver. Select an explicit CB1 Dolby Vision circuit to use its reconstruction and transport contract. [CB1 Dolby Vision reconstruction](../../CB1/docs/ALGORITHMS.md#dolby-vision-reference)

## HDR10+ Native

**Purpose.** Send the original HDR10+ dynamic metadata with the decoded HDR picture on compatible HDMI links.

The explicit HDR10+ native circuit uses decoded PQ pixels and binds the original dynamic metadata to each accepted presentation. The HDMI path needs an HDR10+ display, a supported driver route and accepted output of at least 10 bits. [HDR10+ metadata and transport](../../CB1/docs/HDR10PLUS.md)

## HDR10+ Kodi default

**Purpose.** Play an HDR10+ source through the ordinary HDR10 output path.

Kodi default uses ordinary HDR10 playback. The explicit HDR10+ Native choice enables the dynamic packet route. If an active native HDR10+ route loses admission, Kodi clears its dynamic metadata and can retain HDR10. [Fallback and metadata ownership](../../CB1/docs/HDR10PLUS.md)

## HDR10

**Purpose.** Play HDR10 with its original PQ transfer and static metadata on a compatible display.

Kodi selects native PQ output and sends the applicable static HDR metadata through the driver. The display maps the result to its own capabilities. [Driver constraints](DRIVER-COVERAGE.md#depth-and-topology)

## HLG

**Purpose.** Play HLG in its original transfer format on a compatible display.

Kodi keeps the HLG transfer characteristic for a compatible output. The CB1 HLG-to-Dolby-Vision circuit has a separate reference normalization stage. [HLG processing contract](../../CB1/docs/SDR-HLG.md#plain-hlg-to-dv-reference)

## SDR

**Purpose.** Play SDR through Kodi’s normal path and use the selected SDR upscaler when the picture is enlarged.

Kodi uses the decoded SDR color and transfer information with its normal color conversion and scaler. When enlargement is needed, the SDR upscaler preference controls the final image filter. [Video upscalers](PERFORMANCE-GUIDE.md#video-upscalers)
