# License map

## Current distribution

This inventory describes the Beta4 release sources. The complete matching
runtime is in the [release source archives](https://github.com/CroqueMr/libreelec-x86-DV/releases/tag/R1.0.0-Beta4);
the main-branch code is not a substitute for those archives.

The modified Kodi program links the shared rendering and creative modules.
Those modules contain GPL-3.0-only code; the current combined executable is
therefore distributed under GPL-3.0-only. This does not change the license of
Linux, unrelated programs, firmware or each upstream source file.

There are 64 files in the runtime source directory: 6 marked GPL-3.0-only,
54 GPL-3.0-or-later, 2 LGPL-2.1-or-later, and 2 build/provenance records without a
file-level SPDX identifier. These are declaration counts, not authorship proof.

## Parts requiring GPLv3

| Part | Files or patch | License constraint |
| --- | --- | --- |
| Creative trim resolution and numeric controls | `dvbridge_creative.c/.h` | GPL-3.0-only; recorded DoViBaker/MPC Video Renderer adaptations |
| Adaptive expansion and shader | `cb1_dv_enhanced.c/.h`, `cb1_dv_enhanced_shader.h` | GPL-3.0-only |
| Shared rendering and transport dispatch | `dvbridge_render.c` | GPL-3.0-only; original additions and creative adaptations share this file |
| Serialization and CM4 payload handling | `dvbridge_metadata.h`, `mpv_dvbridge_cm4.h`, `dvbridge_metadata_bounds.h` | GPL-3.0-or-later; inherited project helpers |
| Core, packing, FEL, Master Reference and processing API | Remaining marked runtime files | GPL-3.0-or-later |
| Persistent GPU-program cache | `dvbridge_cache.c/.h` | GPL-3.0-or-later; adapted from Hades RC2 |
| HDR10 AI runtime | `cb1_hdr10_*.c/.h`, `cb1_l1l3_model.c/.h` | GPL-3.0-or-later, except the LGPL filter |
| GPU processing additions | `libplacebo-9913-processing.patch`, `9915-hdr10-linear-conversion`, `9916-fel-filter` | Explicit GPL-3.0-or-later additions alongside retained LGPL upstream code |
| Kodi DV integration | Renderer, AI-source, output-state, VAAPI-scaler and marked UI helpers | GPL-3.0-or-later declarations, independently of the engine directory |

The static-library build lists creative, Adaptive and shared rendering objects
unconditionally. Turning AI off, selecting Standard/Master, disabling a mode or
using a shared library does not remove their licensing requirements.

The patched decoder also includes `dvbridge_metadata_bounds.h` outside the
renderer opt-in. `ENABLE_DVBRIDGE=OFF` is not a GPLv2 build.

## Runtime source inventory

Paths are relative to `CB1/src/`. SPDX identifiers describe the individual
files; the combined program must also satisfy its linked dependencies.

| File | Header declaration |
| --- | --- |
| [cb1_circuit.c](../src/cb1_circuit.c) | GPL-3.0-or-later |
| [cb1_circuit.h](../src/cb1_circuit.h) | GPL-3.0-or-later |
| `cb1_master_ipt.c/.h`, `cb1_master_ipt_shader.h` (normal build disabled) | GPL-3.0-or-later |
| `cb1_dv_enhanced_shader.h` (release sources) | GPL-3.0-only |
| `cb1_dv_enhanced.c` (release sources) | GPL-3.0-only |
| `cb1_dv_enhanced.h` (release sources) | GPL-3.0-only |
| [cb1_hdr10_ai.c](../src/cb1_hdr10_ai.c) | GPL-3.0-or-later |
| [cb1_hdr10_ai.h](../src/cb1_hdr10_ai.h) | GPL-3.0-or-later |
| [cb1_hdr10_extrema.c](../src/cb1_hdr10_extrema.c) | GPL-3.0-or-later |
| [cb1_hdr10_extrema.h](../src/cb1_hdr10_extrema.h) | GPL-3.0-or-later |
| [cb1_hdr10_features.c](../src/cb1_hdr10_features.c) | GPL-3.0-or-later |
| [cb1_hdr10_features.h](../src/cb1_hdr10_features.h) | GPL-3.0-or-later |
| [cb1_hdr10_filter.c](../src/cb1_hdr10_filter.c) | LGPL-2.1-or-later |
| [cb1_hdr10_filter.h](../src/cb1_hdr10_filter.h) | LGPL-2.1-or-later |
| [cb1_hdr10_grid.h](../src/cb1_hdr10_grid.h) | GPL-3.0-or-later |
| [cb1_hdr10_ingress.c](../src/cb1_hdr10_ingress.c) | GPL-3.0-or-later |
| [cb1_hdr10_ingress.h](../src/cb1_hdr10_ingress.h) | GPL-3.0-or-later |
| [cb1_hdr10_quantiles.c](../src/cb1_hdr10_quantiles.c) | GPL-3.0-or-later |
| [cb1_hdr10_quantiles.h](../src/cb1_hdr10_quantiles.h) | GPL-3.0-or-later |
| [cb1_hdr10_spatial.c](../src/cb1_hdr10_spatial.c) | GPL-3.0-or-later |
| [cb1_hdr10_spatial.h](../src/cb1_hdr10_spatial.h) | GPL-3.0-or-later |
| [cb1_hdr10_statistics.c](../src/cb1_hdr10_statistics.c) | GPL-3.0-or-later |
| [cb1_hdr10_statistics.h](../src/cb1_hdr10_statistics.h) | GPL-3.0-or-later |
| [cb1_hdr10_temporal.c](../src/cb1_hdr10_temporal.c) | GPL-3.0-or-later |
| [cb1_hdr10_temporal.h](../src/cb1_hdr10_temporal.h) | GPL-3.0-or-later |
| [cb1_l1l3_model.c](../src/cb1_l1l3_model.c) | GPL-3.0-or-later |
| [cb1_l1l3_model.h](../src/cb1_l1l3_model.h) | GPL-3.0-or-later |
| `cb1_master_reference.c` (release sources) | GPL-3.0-or-later |
| `cb1_master_reference.h` (release sources) | GPL-3.0-or-later |
| [cb1_processing.c](../src/cb1_processing.c) | GPL-3.0-or-later |
| [cb1_processing.h](../src/cb1_processing.h) | GPL-3.0-or-later |
| [CMakeLists.txt](../src/CMakeLists.txt) | No file SPDX; build/provenance record |
| `dvbridge_cache.c` (release sources) | GPL-3.0-or-later |
| `dvbridge_cache.h` (release sources) | GPL-3.0-or-later |
| [dvbridge_core.c](../src/dvbridge_core.c) | GPL-3.0-or-later |
| [dvbridge_core.h](../src/dvbridge_core.h) | GPL-3.0-or-later |
| [dvbridge_creative.c](../src/dvbridge_creative.c) | GPL-3.0-only |
| [dvbridge_creative.h](../src/dvbridge_creative.h) | GPL-3.0-only |
| [dvbridge_dmabuf.c](../src/dvbridge_dmabuf.c) | GPL-3.0-or-later |
| [dvbridge_dmabuf.h](../src/dvbridge_dmabuf.h) | GPL-3.0-or-later |
| [dvbridge_fel_seek.h](../src/dvbridge_fel_seek.h) | GPL-3.0-or-later |
| [dvbridge_fel_vpp.c](../src/dvbridge_fel_vpp.c) | GPL-3.0-or-later |
| [dvbridge_fel_vpp.h](../src/dvbridge_fel_vpp.h) | GPL-3.0-or-later |
| [dvbridge_fel.c](../src/dvbridge_fel.c) | GPL-3.0-or-later |
| [dvbridge_fel.h](../src/dvbridge_fel.h) | GPL-3.0-or-later |
| [dvbridge_gl_frame.c](../src/dvbridge_gl_frame.c) | GPL-3.0-or-later |
| [dvbridge_gl_frame.h](../src/dvbridge_gl_frame.h) | GPL-3.0-or-later |
| [dvbridge_gl_pack.c](../src/dvbridge_gl_pack.c) | GPL-3.0-or-later |
| [dvbridge_gl_pack.h](../src/dvbridge_gl_pack.h) | GPL-3.0-or-later |
| [dvbridge_metadata_bounds.h](../src/dvbridge_metadata_bounds.h) | GPL-3.0-or-later |
| [dvbridge_metadata.h](../src/dvbridge_metadata.h) | GPL-3.0-or-later |
| [dvbridge_pack_sources.h.in](../src/dvbridge_pack_sources.h.in) | GPL-3.0-or-later |
| [dvbridge_placebo.c](../src/dvbridge_placebo.c) | GPL-3.0-or-later |
| [dvbridge_placebo.h](../src/dvbridge_placebo.h) | GPL-3.0-or-later |
| [dvbridge_policy.c](../src/dvbridge_policy.c) | GPL-3.0-or-later |
| [dvbridge_policy.h](../src/dvbridge_policy.h) | GPL-3.0-or-later |
| [dvbridge_render.c](../src/dvbridge_render.c) | GPL-3.0-only |
| [dvbridge_render.h](../src/dvbridge_render.h) | GPL-3.0-or-later |
| [mpv_dvbridge_cm4.h](../src/mpv_dvbridge_cm4.h) | GPL-3.0-or-later |
| [pack_gles300.frag](../src/pack_gles300.frag) | GPL-3.0-or-later |
| [pack_gles300.vert](../src/pack_gles300.vert) | GPL-3.0-or-later |
| [PROVENANCE.json](../src/PROVENANCE.json) | No file SPDX; build/provenance record |

## Dependencies and other components

| Component | Actual scope |
| --- | --- |
| FFmpeg RPU/raw metadata and MVC changes | Retain upstream LGPL-2.1-or-later file notices; selected GPL codecs/build options affect the library combination |
| FFmpeg release recipe | `--enable-gpl --enable-version3 --enable-openssl`; declared GPL-3.0-or-later |
| OpenSSL 3.6.4 | Apache-2.0; FFmpeg's GPL build requires version3 for OpenSSL 3 |
| Original libplacebo | LGPL-2.1-or-later; not all modified-library additions use that license |
| `cb1_hdr10_filter.c/.h` | LGPL-2.1-or-later, FFmpeg attribution retained |
| NumPy-derived summation | BSD-3-Clause notice retained in the relevant AI files and `LICENSES/BSD-NumPy.txt` |
| LightGBM runtime | MIT; this does not license the trained model or the surrounding AI adapter |
| Linux, Intel/AMD display patches and AMD HDMI 3D | Existing MIT/GPL-2.0-compatible file terms; no identified GPLv3 dependency from these changes |
| NVIDIA open kernel modules | MIT OR GPL-2.0-only |
| NVIDIA VAAPI bridge | MIT |
| NVIDIA userspace and firmware | Separate NVIDIA agreement; redistributed binaries must remain unmodified and retain that agreement |
| Build tools and tests | Per-file terms; using a GPL tool does not by itself change the license of its output |

NVIDIA's Hades-derived Kodi output adapter is separate from the vendor driver:
the adapter's GPL-3.0-or-later notice remains applicable even though the open
kernel modules have MIT/GPLv2 terms.

## Model rights record

The model README declares GPL-3.0-or-later. The locked model record still contains
`redistribution_cleared: false`, and its bundle contains an origin-status hash
rather than the underlying rights record. These facts do not prove unlawful
training or redistribution, but do not establish clearance either.

A rights-controlled original model may be offered under another license after
its provenance and applicable commitments are established. Do not change the
clearance flag or infer model rights from LightGBM's MIT license.

## A GPLv2-compatible variant

No GPLv2-compatible variant is established by this audit.

- Contributions wholly controlled by the project may receive an additional MIT,
  BSD or GPL-2.0-or-later grant from the relevant rightsholders.
- Third-party GPLv3-derived code needs an appropriate additional permission or a
  replacement not derived from that protected implementation.
- Shared renderer, metadata, Kodi helpers, patched libplacebo and FFmpeg/TLS
  configuration must all be addressed, not just creative trims or AI.
- Preserve the licenses of already distributed versions. A new grant does not
  revoke recipients' earlier GPL rights.

Moving code into another repository or adding an API is not, by itself, a
license workaround. Distinct programs aggregated in an image retain their own
terms; tightly linked parts of one program are a different case.

[GNU compatibility FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#v2v3Compatibility)
· [GNU linking FAQ](https://www.gnu.org/licenses/gpl-faq.en.html#IfLibraryIsGPL)
· [GPLv3 section 14](https://www.gnu.org/licenses/gpl.en.html#section14)
· [FFmpeg build/license rules](https://ffmpeg.org/legal.html).

## Provenance and verification limits

The recorded creative sources include
[DoViBaker](https://github.com/erazortt/DoViBaker/tree/ffba39830b694ddca0bf5f73dcf1b462713bb7f4)
and [MPC Video Renderer](https://github.com/Aleksoid1978/VideoRenderer/tree/6bb2f3d702993f04e888bf5abd0944a83333b3c5).
The Hades cache/output adaptation is pinned to
[Hades RC2](https://github.com/hadesdevls/LibreELEC-Hades/tree/69fc36199f0d5f5d1e5bb4d42f45656e256a6e35).
[Creative attribution](CREATIVE-MAPPING.md) retains the detailed source record.

The integrity verifier passes for the local engine, 26 dependency patches, locked
model and retained license files. This confirms recorded bytes, not ownership or
the complete legal status of every dependency in an installed image.
`owned-sources.json` is a checksum inventory, not a copyright assignment.

This review does not establish patent freedom, proprietary-mapper certification,
or complete third-party rights clearance. No license grant or source notice was
changed by the documentation update.
