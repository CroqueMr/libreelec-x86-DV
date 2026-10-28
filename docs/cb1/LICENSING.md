# Licensing and credits

Licenses apply to individual components, not uniformly to the entire image.
The combined modified Kodi executable requires **GPL-3.0-only** in the current
build. Existing upstream files retain their own notices.

| Part | Current terms |
| --- | --- |
| Original project rendering, Adaptive, creative trims and player adapters | GPL-2.0-or-later where granted; third-party notices retained |
| Replacement metadata serialization, cache, transport and composition helpers | GPL-2.0-or-later; provenance in the engine migration record |
| HDR10 AI analysis and inference adapter | GPL-2.0-or-later; FFmpeg-derived filter remains LGPL-2.1-or-later |
| Modified libplacebo additions | Per-file GPL-2.0-or-later/LGPL-2.1-or-later terms; upstream notices retained |
| FFmpeg libraries in this build | GPL-3.0-or-later, with `--enable-gpl --enable-version3` |
| Modified Kodi executable in this build | GPL-3.0-only under the selected combined-build conditions; compatible project adapters do not change that |
| Intel/AMD display-driver and HDMI 3D changes | Existing MIT/GPL-2.0-compatible file notices; Linux remains GPL-2.0-only |
| LightGBM library | MIT |
| L1/L3 model assets | GPL-2.0-or-later, owner's additional grant dated 2026-10-22 |
| NVIDIA open kernel modules | MIT OR GPL-2.0-only |
| NVIDIA userspace/firmware | NVIDIA redistribution terms, not GPL |
| Original project tooling/documentation and other dependencies | MIT where declared; otherwise their retained upstream/file terms |

The GPLv2 migration covers the project's additions and replacements, not the
complete image. FFmpeg retains `--enable-gpl --enable-version3` and the selected
Kodi build retains its GPLv3 conditions. An API or shared-library boundary does
not remove those requirements. [Engine license details](../../CB1/docs/LICENSING.md).

Source archives provide release sources, patches, the model and build material.
Keep source and vendor inputs available alongside the binaries, with notices and
license texts. The model lock records the owner's additional grant and
`redistribution_cleared: true`; weights and normalization are unchanged.
No proprietary Dolby SDK is used. This license inventory is not patent clearance.

Published Beta5's historical inventory is retained in the
[license map](../../CB1/docs/LICENSE-MAP.md). The current replacements and grants
are documented in the [migration record](../../CB1/docs/GPL2-MIGRATION.md).
Offline comparisons do not certify hardware or establish patent clearance.

The 2026-10-28 HDR transport additions do not import, copy, translate or adapt
Hades code. They use the pre-existing candidate and original Linux/NVIDIA
interfaces under compatible per-file terms. Existing Hades attribution below
refers to earlier integration and is retained. No new GPLv3 dependency is added;
this does not change the combined-image licensing stated above.

## Credits

- [dangerouslaser](https://github.com/dangerouslaser): Global rendering-engine optimizations.
- [hadesdevls](https://github.com/hadesdevls): NVIDIA integration adapted from LibreELEC Hades.
- [CinemaOne](https://github.com/cinema-ONE) and [popcornmix](https://github.com/popcornmix): Blu-ray 3D work and stereo-output selection.
- [dovi_tool](https://github.com/quietvoid/dovi_tool): Dolby Vision tooling and references.
- Development assistance: OpenAI ChatGPT, GPT-6 Astra and Codex.

Original source attribution is retained. No certification or affiliation with
Dolby, LibreELEC, Kodi, Intel, AMD or NVIDIA is claimed.
