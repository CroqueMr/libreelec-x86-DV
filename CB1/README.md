# CB1

**CB1 0.3** is an open-source Dolby Vision processing engine, linked into the
player through a native C API. It is not a separate service or external player.

## Rendering circuits

| Source | Circuit | Output |
| --- | --- | --- |
| Dolby Vision | Standard | Performance-oriented TV-Led Dolby Vision |
| Dolby Vision | Master Reference | Reference-oriented TV-Led Dolby Vision |
| Dolby Vision | Adaptive HDR Mapping | Metadata-guided highlight/midtone expansion, TV-Led output |
| Dolby Vision | HDR10 Reference Basic | Source-guided HDR10 conversion |
| Dolby Vision | HDR10 Reference Expert | Display-reference HDR10 conversion with compatible creative controls |
| HDR10 | Dolby Vision Reference AI | AI-estimated L1/L3 without an enhancement grade |
| HDR10 | Adaptive HDR Mapping AI | AI-guided expansion with Dolby Vision output |

Expert and Adaptive modes use the display profile. AI modes share the included
[CB1-L1L3 model](models/l1l3/README.md). Native HDR10, HLG and SDR remain
player-owned. [Profile coverage](../README.md#supported-dolby-vision-profiles).

## Integration

The player owns decoding, timing, audio, subtitles, UI and presentation. CB1 owns
reconstruction, processing and output metadata. The C API shares frame identity,
FFmpeg metadata and libplacebo/GLES resources; it is not a network API.

LibreELEC supports Intel and AMD integrated graphics. Dedicated Radeon RX
5000/6000/7000 and GeForce GTX 16 / RTX 20/30/40/50 support is experimental.
Hardware support and processing support are separate.
[Hardware](../docs/cb1/HARDWARE.md).

AMD HDMI 3D uses Kodi's native stereoscopic path, outside CB1.
[3D playback](../docs/cb1/3D.md).

## Source layout

| Path | Content |
| --- | --- |
| `src/` | Processing library and API |
| `patches/` | Matched FFmpeg/libplacebo patches |
| `models/l1l3/` | LightGBM model and runtime contract |
| `config/` | Dependencies, versions and source manifests |
| `tests/` | Regression and numerical checks |
| `docs/` | Algorithms, circuit contracts and integration |

[Processing](../docs/cb1/PROCESSING.md) · [Algorithms](docs/ALGORITHMS.md)
· [Master Reference](docs/MASTER-REFERENCE.md)
· [Licensing](../docs/cb1/LICENSING.md)

GPU requirements depend on the circuit and content. Visible GUI and heavy
conversions can exceed low-powered GPUs. Test media and training datasets are
not included.
