# Licensing

The license depends on the module. Do not treat the engine name as one blanket
license grant. [File map and GPLv2 constraints](LICENSE-MAP.md).

| Material | Terms |
| --- | --- |
| Original FEL queue, seek/VPP, metadata mapping and player adapters | GPL-2.0-or-later; owner's additional grant; implementations unchanged except separately recorded replacements |
| Original HDR10 AI, model adapter, circuit and policy modules | GPL-2.0-or-later; retained NumPy BSD notices where applicable |
| Original frame transaction, Master Reference contract, processing preparation, GL frame and CPU Adaptive model | GPL-2.0-or-later; owner's additional grant, implementation unchanged |
| Creative scalar implementation and private trim math | GPL-2.0-or-later; original CM4/resolver/fitter plus replacement scalar kernels |
| Adaptive compute shader, replacement GPU trims and carrier kernels | GPL-2.0-or-later; original expansion/statistics and compatible replacement kernels |
| `dvbridge_render.c` and fused colour/composition helper | GPL-2.0-or-later; original integration and replacement numerical/transport/composition kernels |
| Replacement cache, metadata bounds, serializer and CM4 wire helpers | GPL-2.0-or-later; [replacement provenance](GPL2-MIGRATION.md) |
| Canonical tunnel shader, GL packer and DMA-BUF import | GPL-2.0-or-later; replacement wire/layout validation and original resource/state adapters |
| Tests and reference operators | Per-file MIT, GPL-3.0-or-later or GPL-3.0-only |
| Original tooling, build wiring and documentation | MIT |
| FFmpeg-derived filter and inherited FFmpeg/libplacebo code | LGPL-2.1-or-later notices retained |
| CB1 libplacebo `9913` processing additions | Original ABI/glue GPL-2.0-or-later; replacement lookup/reshape emitters and reference code LGPL-2.1-or-later; upstream notices retained |
| Original libplacebo `9915` linear-conversion and `9916` filter/reference additions | GPL-2.0-or-later; upstream LGPL code/notices unchanged |
| Replacement Kodi output-state transaction | GPL-2.0-or-later; original project-specific Kodi adapters receive the owner's grant; upstream Kodi terms retained |
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
The published NVIDIA output-state adapter, half-float output support and driver
integration reused LibreELEC Hades RC2 at the same pinned revision. The local
output-state replacement is documented in [adapter migration](ADAPTER-MIGRATION.md);
compatible upstream integrations retain their notices. NVIDIA open kernel modules use
MIT OR GPL-2.0-only; NVIDIA userspace and
firmware retain their vendor terms in the image's license material. The VAAPI
bridge is MIT-licensed. CB1's processing algorithms and model are unchanged by
the NVIDIA backend.
[Creative-source attribution](CREATIVE-MAPPING.md) records source revisions
and retained notices.

Redistribution requires corresponding source, build material and notices for
the complete selected product. CB1 alone is not the complete source of a
LibreELEC image.

LibreELEC, Kodi and dependency declarations are retained, not reinterpreted by
this migration. Beta5's FFmpeg configuration still enables GPL/version3 and
OpenSSL 3, under its original dependency conditions. Separate Linux, driver,
tool and firmware components keep their own licenses. Compatible project
additions do not establish a GPLv2-only complete image.

The model's dependency lock records the owner's additional grant. Its trained
weights, normalization and artifact ID are unchanged.

The GPLv2-compatible migration concerns project additions. FFmpeg retains the
conditions of the exact vanilla LibreELEC reference. The [migration record](GPL2-MIGRATION.md)
lists grants, completed replacements and remaining complete-product checks.

No proprietary Dolby SDK or media are included.
