# CB1

CB1 is an open-source Dolby Vision processing engine with HDR10 conversion.
**CB1 0.1** is a C11 static library linked into the player's render path, without
a separate service or external player.


## Dolby Vision profiles

| Profile | Support |
| --- | --- |
| 5 | Yes |
| 7 MEL | Yes |
| 7 FEL | Yes, including enhancement-layer reconstruction |
| 8.1 | Yes |
| 8.2 | Yes |
| 8.4 | Yes |
| 10 | Yes |
| 9, legacy profiles, 20 | No |

CM2.9 and CM4 metadata are supported. Profile support does not imply that every
source contains creative trims or that every output mode applies every field.
[Algorithms and metadata](docs/ALGORITHMS.md) explains the processing rules.

## Conversions

| Source | Mode | Output | Result |
| --- | --- | --- | --- |
| Dolby Vision | DV Standard (TV-Led) | Dolby Vision, TV-Led | Preserve the authored Dolby Vision presentation, with final mapping by the TV |
| Dolby Vision | DV Enhanced - Natural and Signature | Dolby Vision, TV-Led | Adapt highlight and color response to the display profile, with two presets: Natural or Signature |
| Dolby Vision | HDR10 Reference Basic | HDR10 | Play Dolby Vision content in HDR10 without a manual TV profile |
| Dolby Vision | HDR10 Reference Expert | HDR10 | Match HDR10 conversion to the display's peak and gamut, using available creative controls |
| HDR10 | DV Reference (AI) | Dolby Vision, TV-Led | Enable TV-Led Dolby Vision from HDR10 while preserving the source image |
| HDR10 | DV Enhanced (AI) - Natural and Signature | Dolby Vision, TV-Led | Adapt HDR10 highlights and colors to the display profile for Dolby Vision output, with two presets: Natural or Signature |

For more details, see [rendering modes and algorithms](docs/ALGORITHMS.md).

Expert and Enhanced require a manual display profile. AI conversion uses the
included [CB1-L1L3 0.1 LightGBM model](models/l1l3/README.md).
Native HDR10, HLG and SDR remain the player's responsibility.

## Documentation

- [Algorithms and metadata](docs/ALGORITHMS.md): pipeline, equations, ratios and coefficients.
- [Circuits](docs/CIRCUITS.md): independently versioned end-to-end paths.
- [Build](docs/BUILD.md) and [API](docs/API.md): dependencies and integration.
- [Licensing](docs/LICENSING.md): licenses and source attribution.

## Repository layout

| Path | Content |
| --- | --- |
| `src/` | Processing library and native API |
| `patches/` | Matched FFmpeg and libplacebo changes |
| `config/` | Dependencies, circuit and license manifests |
| `models/l1l3/` | LightGBM model, normalization and runtime contract |
| `tests/` | Regression and numerical controls |
| `tools/` | Source verification helpers |
| `docs/` | Technical and integration documentation |
| `LICENSES/` | Retained license texts and notices |

## Integration

The player owns decoding, timing, audio, subtitles, UI and presentation. CB1
owns reconstruction, processing and output metadata. Its native C API shares
FFmpeg metadata and libplacebo/GLES resources, not a network API.

The LibreELEC integration provides Intel and experimental AMD display support.
Performance may vary by hardware. Report playback problems to the integration
repository with the exact CPU/GPU, display, connection chain and build version.

## Known issues

- Some frame drops with Profile 7 FEL on a small number of files on N100/N150.

Test media and training datasets are excluded. No affiliation with or certification
by Dolby, Intel or AMD.
