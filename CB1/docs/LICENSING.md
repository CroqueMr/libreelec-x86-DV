# Licensing

The license depends on the module. Do not treat the engine name as one blanket
license grant. [File map and GPLv2 constraints](LICENSE-MAP.md).

| Material | Terms |
| --- | --- |
| Remaining fused transport, FEL, import and rendering adapters | GPL-3.0-or-later pending migration |
| Original HDR10 AI, model adapter, circuit and policy modules | GPL-2.0-or-later; retained NumPy BSD notices where applicable |
| Original frame transaction, Master Reference contract, processing preparation, GL frame and CPU Adaptive model | GPL-2.0-or-later; owner's additional grant, implementation unchanged |
| Creative scalar implementation and private trim math | GPL-2.0-or-later; original CM4/resolver/fitter plus replacement scalar kernels |
| `cb1_dv_enhanced_shader.h`, `dvbridge_render.c` | GPL-3.0-only |
| Replacement cache, metadata bounds, serializer and CM4 wire helpers | GPL-2.0-or-later; [replacement provenance](GPL2-MIGRATION.md) |
| Canonical tunnel shader and GL packer | GPL-2.0-or-later; replacement bit encoder and original resource/state adapter; fused renderer packing remains unresolved |
| Tests and reference operators | Per-file MIT, GPL-3.0-or-later or GPL-3.0-only |
| Original tooling, build wiring and documentation | MIT |
| FFmpeg-derived filter and inherited FFmpeg/libplacebo code | LGPL-2.1-or-later notices retained |
| CB1 libplacebo processing additions | GPL-3.0-or-later; combined modified library distributed under GPLv3-compatible terms |
| LightGBM | MIT |
| L1/L3 model assets | GPL-2.0-or-later, owner grant dated 2026-10-22 |
| NumPy-derived duration summation | BSD-3-Clause |
| FFmpeg-derived analysis coefficients | LGPL-2.1-or-later |

License texts and credits are in `LICENSES/`. Source origins are recorded in
`src/PROVENANCE.json` and `config/extraction-origins.json`.

References and adapted work include dovi_tool, PGenerator-Plus,
ofxRPI4Window, DoViBaker, MPC Video Renderer, YBLOD, LibreELEC Hades and ETSI GS CCM 001.
The published Beta5 cache was adapted from LibreELEC Hades `v1.0-rc2`
(`69fc36199f0d5f5d1e5bb4d42f45656e256a6e35`), GPL-3.0-or-later. The local
replacement uses libplacebo's public cache API and POSIX file operations.
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

The current static library includes GPL-3.0-only fused rendering/Adaptive code even
without AI. The linked Kodi program therefore uses GPL-3.0-only, while separate
Linux, driver, tool and firmware components retain their own licenses. FFmpeg is
also built with GPL and version3 enabled; its OpenSSL 3 dependency is Apache-2.0.
Changing the engine's directory or linkage does not produce a GPLv2 variant.

The model's dependency lock records the owner's additional grant. Its trained
weights, normalization and artifact ID are unchanged.

The GPLv2-compatible migration concerns project additions. FFmpeg retains the
conditions of the exact vanilla LibreELEC reference. The [migration record](GPL2-MIGRATION.md)
lists grants, completed replacements and unresolved linked components.

No proprietary Dolby SDK or media are included.
