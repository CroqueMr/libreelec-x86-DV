# Hardware support

## Integrated graphics

| Family | Dolby Vision support |
| --- | --- |
| Intel Core 8th generation and newer | Supported |
| Intel Core Ultra Series 1 / 2, including 200V | Supported |
| Intel N-series, including N100 / N150 | Supported |
| AMD Ryzen 2000G / 3000G and corresponding mobile APUs | Supported |
| AMD Ryzen 4000 / 5000 APUs, 6000, 7030 / 7035, 7040 / 8040, 8000G, AI 300 | Supported |

AMD entries refer to processors with integrated graphics, not every desktop CPU
sharing the same Ryzen generation number.

## Dedicated graphics: experimental

| Family | Representative models | Status |
| --- | --- | --- |
| AMD Radeon RX 5000, RDNA 1 | RX 5500 XT, 5600 XT, 5700 / 5700 XT | Experimental |
| AMD Radeon RX 6000, RDNA 2 | RX 6400, 6600, 6700 XT, 6800, 6900 XT | Experimental |
| AMD Radeon RX 7000, RDNA 3 | RX 7600, 7700 XT, 7800 XT, 7900 XT / XTX | Experimental |
| NVIDIA GeForce GTX 16, Turing | GTX 1650, 1660 | Experimental |
| NVIDIA GeForce RTX 20, Turing | RTX 2060, 2070, 2080 | Experimental |
| NVIDIA GeForce RTX 30, Ampere | RTX 3060, 3070, 3080, 3090 | Experimental |
| NVIDIA GeForce RTX 40, Ada | RTX 4060, 4070, 4080, 4090 | Experimental |
| NVIDIA GeForce RTX 50, Blackwell | RTX 5060, 5070, 5080, 5090 | Experimental |

The AMD Dolby Vision driver covers selected DCN 1.x, 2.x and 3.x display engines.
RX 9000 / DCN 4, Polaris RX 400 / 500 and discrete Vega cards are outside its
current allowlist. Vega-based Ryzen APUs listed above use a different display path.

NVIDIA uses matched 615.78.08 open kernel modules, firmware, proprietary userspace
and a VAAPI-to-NVDEC bridge. Pascal / GTX 10 and earlier are not supported by this
driver branch. The open modules require Turing or newer.
[NVIDIA driver requirements](https://github.com/NVIDIA/open-gpu-kernel-modules#compatible-gpus)
and [licensing](LICENSING.md).

## Output and performance

Dolby Vision output requires a compatible HDMI display and an admitted driver
route. Unavailable Dolby Vision outputs retain eligible HDR10 conversions or
native Kodi playback. DP adapters and active converters are not generally
supported for Dolby Vision signaling.

Other GPUs can use Dolby Vision processing to HDR10 where decoding and GPU
processing are available, without custom Dolby Vision HDMI output.

Performance depends on hardware, content and rendering mode. Report problems
with the exact CPU/GPU, display, connection chain, build version and `kodi.log`.

## AMD HDMI 3D

MVC Blu-ray ISO, HDMI frame packing, side-by-side and top-and-bottom use a
separate native Kodi path. The additional HDMI 3D driver support is AMD-specific;
it is not an Intel or NVIDIA 3D-output claim.

Beta4 feedback confirms MVC frame-packed 1080p24 and half-SBS 1080p60 on an
RX 7600 with a JVC projector. This is a 3D validation, not validation of Dolby
Vision on a physical Dolby Vision display.
[Reported setup](https://forum.libreelec.tv/thread/30362-x86-64-dolby-vision-w-fel-full-3d-for-pc-intel-amd-nvidia/?postID=208017#post208017).

[3D setup](3D.md) · [Playback settings](PLAYBACK.md)
