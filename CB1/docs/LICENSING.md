# Licensing

The license depends on the module. Do not treat the engine name as one blanket
license grant. [File map and GPLv2 constraints](LICENSE-MAP.md).

| Material | Terms |
| --- | --- |
| Metadata/transport, FEL, Master Reference, processing API and AI runtime | GPL-3.0-or-later |
| `dvbridge_creative.c/.h`, `cb1_dv_enhanced.c/.h`, `cb1_dv_enhanced_shader.h`, `dvbridge_render.c` | GPL-3.0-only |
| Hades-derived `dvbridge_cache.c/.h` | GPL-3.0-or-later |
| Tests and reference operators | Per-file MIT, GPL-3.0-or-later or GPL-3.0-only |
| Original tooling, build wiring and documentation | MIT |
| FFmpeg-derived filter and inherited FFmpeg/libplacebo code | LGPL-2.1-or-later notices retained |
| CB1 libplacebo processing additions | GPL-3.0-or-later; combined modified library distributed under GPLv3-compatible terms |
| LightGBM | MIT |
| L1/L3 model assets | Declared GPL-3.0-or-later; redistribution-clearance record unresolved |
| NumPy-derived duration summation | BSD-3-Clause |
| FFmpeg-derived analysis coefficients | LGPL-2.1-or-later |

License texts and credits are in `LICENSES/`. Source origins are recorded in
`src/PROVENANCE.json` and `config/extraction-origins.json`.

References and adapted work include dovi_tool, PGenerator-Plus,
ofxRPI4Window, DoViBaker, MPC Video Renderer, YBLOD, LibreELEC Hades and ETSI GS CCM 001.
The program-cache helper is adapted from LibreELEC Hades `v1.0-rc2`
(`69fc36199f0d5f5d1e5bb4d42f45656e256a6e35`), GPL-3.0-or-later.
Kodi's mode-hold and presentation-stall policies retain Hades' GPL-2.0-or-later notices.
The NVIDIA output-state adapter, half-float output support and driver integration
reuse LibreELEC Hades RC2 at the same pinned revision, with original notices
retained. NVIDIA open kernel modules use MIT OR GPL-2.0-only; NVIDIA userspace and
firmware retain their vendor terms in the image's license material. The VAAPI
bridge is MIT-licensed. CB1's processing algorithms and model are unchanged by
the NVIDIA backend.
[Creative-source attribution](CREATIVE-MAPPING.md) records source revisions
and retained notices.

Redistribution requires corresponding source, build material and notices for
the complete selected product. CB1 alone is not the complete source of a
LibreELEC image.

The current static library includes GPL-3.0-only creative/rendering objects even
without AI. The linked Kodi program therefore uses GPL-3.0-only, while separate
Linux, driver, tool and firmware components retain their own licenses. FFmpeg is
also built with GPL and version3 enabled; its OpenSSL 3 dependency is Apache-2.0.
Changing the engine's directory or linkage does not produce a GPLv2 variant.

The model's dependency lock records `redistribution_cleared: false`. Hash integrity
does not establish ownership, training-data rights or a redistribution permission.

The planned GPLv2-compatible migration concerns project additions. FFmpeg retains
the conditions of the exact vanilla LibreELEC reference. No runtime license grant,
model asset or rendering behavior has been changed by the provenance audit.

No proprietary Dolby SDK or media are included.
