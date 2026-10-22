# Licensing and credits

Licenses apply to individual components, not uniformly to the entire image.
The combined modified Kodi executable requires **GPL-3.0-only** in the current
build. Existing upstream files retain their own notices.

| Part | Current terms |
| --- | --- |
| Creative trim resolver, Adaptive calculation/shader and shared rendering implementation | GPL-3.0-only |
| DV metadata serialization, packing, reconstruction/FEL helpers, Master Reference and processing API | GPL-3.0-or-later |
| Persistent shader cache adapted from Hades | GPL-3.0-or-later |
| HDR10 AI analysis and inference adapter | GPL-3.0-or-later; FFmpeg-derived filter remains LGPL-2.1-or-later |
| Modified libplacebo processing, linear-conversion and FEL-filter additions | GPL-3.0-or-later; upstream LGPL notices retained |
| FFmpeg libraries in this build | GPL-3.0-or-later, with `--enable-gpl --enable-version3` |
| Kodi's added DV renderer/output adapters and marked helpers | GPL-3.0-or-later; upstream Kodi is GPL-2.0-or-later |
| Intel/AMD display-driver and HDMI 3D changes | Existing MIT/GPL-2.0-compatible file notices; Linux remains GPL-2.0-only |
| LightGBM library | MIT |
| L1/L3 model assets | Declared GPL-3.0-or-later; redistribution-clearance record unresolved |
| NVIDIA open kernel modules | MIT OR GPL-2.0-only |
| NVIDIA userspace/firmware | NVIDIA redistribution terms, not GPL |
| Original project tooling/documentation and other dependencies | MIT where declared; otherwise their retained upstream/file terms |

The GPLv3 requirement is not confined to a single conversion mode. Creative and
shared rendering modules are linked unconditionally; disabling a mode is not a
GPLv2 build. An API or shared-library boundary does not by itself remove license
requirements. [Engine license details](../../CB1/docs/LICENSING.md).

Source archives provide release sources, patches, the model and build material.
Keep source and vendor inputs available alongside the binaries, with notices and
license texts. The model lock still records `redistribution_cleared: false`;
this needs a provenance/rights confirmation, not a silent flag change.
No proprietary Dolby SDK is used. This license inventory is not patent clearance.

The GPLv2-compatible migration targets the project's additions, preserving the
exact vanilla LibreELEC dependency conditions. Existing license grants and Beta5
rendering are unchanged. The migration is not yet a qualified distributable build.

## Credits

- [dangerouslaser](https://github.com/dangerouslaser): Global rendering-engine optimizations.
- [hadesdevls](https://github.com/hadesdevls): NVIDIA integration adapted from LibreELEC Hades.
- [CinemaOne](https://github.com/cinema-ONE) and [popcornmix](https://github.com/popcornmix): Blu-ray 3D work and stereo-output selection.
- [dovi_tool](https://github.com/quietvoid/dovi_tool): Dolby Vision tooling and references.
- Development assistance: OpenAI ChatGPT, GPT-6 Astra and Codex.

Original source attribution is retained. No certification or affiliation with
Dolby, LibreELEC, Kodi, Intel, AMD or NVIDIA is claimed.
