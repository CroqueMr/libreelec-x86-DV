# Beta5 licensing migration

Work in progress. The linked program still contains GPLv3 dependencies.
This record does not change the licenses of published Beta5 releases.

## Grants

On 2026-10-22 the project owner authorized GPL-2.0-or-later distribution of
their original contributions. Third-party code and adaptations are excluded
from that authorization and retain their own terms until replaced or separately
authorized. File-by-file provenance determines the scope of any notice change.

The owner also confirmed authorship of the trained L1/L3 model and granted
GPL-2.0-or-later for the exact [runtime bundle](../models/l1l3/LICENSE.md).
Weights, normalization, model ID and predictions are unchanged.

The additional grant is applied to these original project modules:
`cb1_circuit.*`, `dvbridge_policy.*`, `cb1_l1l3_model.*`,
`cb1_hdr10_ai.*`, `cb1_hdr10_extrema.*`, `cb1_hdr10_features.*`,
`cb1_hdr10_grid.h`, `cb1_hdr10_ingress.*`, `cb1_hdr10_quantiles.*`,
`cb1_hdr10_spatial.*`, `cb1_hdr10_statistics.*` and `cb1_hdr10_temporal.*`.
Their implementation text is unchanged. The NumPy BSD-3-Clause summation notices
remain in the features/temporal modules. The FFmpeg-derived filter retains
LGPL-2.1-or-later. These individual grants do not relicense the combined program.

The same grant covers these original frame/control modules, also without
implementation changes:

| Files | Original project portion | Not covered by this grant |
| --- | --- | --- |
| `dvbridge_core.c/.h` | Candidate ownership, geometry and presentation commit | Imported serializer implementation, replaced separately |
| `cb1_master_reference.c/.h` | FFmpeg metadata validation/copying into the exact-reference contract | libplacebo reconstruction shaders |
| `cb1_processing.c/.h` | Original bounds certification, table preparation and cache/admission management | Processing shader additions in libplacebo |
| `cb1_dv_enhanced.c/.h` | Original expansion curve, scalar model and temporal state | Creative trim adaptations and expansion/packing GPU shader |
| `dvbridge_gl_frame.c/.h` | Native decoded-texture wrapping through public libplacebo/GLES APIs | NVIDIA import and unresolved FEL/VAAPI adaptations |

Calling or declaring types from a separately licensed module does not grant
rights to its implementation. The combined program still includes unresolved
GPLv3 portions. Historical extraction records and third-party notices remain.

## Replacements

| Component | Implementation basis | Compatibility check |
| --- | --- | --- |
| `dvbridge_cache.c/.h` | Public pinned libplacebo cache API and its version-1 storage format, LGPL-2.1-or-later; POSIX temporary-file/rename operations | Same objects, eviction, load counts, save results and persisted bytes as the separately compiled Beta5 wrapper; corruption and persistence-failure tests |
| `dvbridge_metadata_bounds.h` | Matched FFmpeg public `AVDOVIMetadata` layout, LGPL-2.1-or-later | Same accepted/rejected storage layouts, alignment, stride and bounds |
| `mpv_dvbridge_cm4.h` | Public field widths and optional-block syntax in MIT dovi_tool `d4ad4ba7` | Same accepted/rejected blocks and exact transport bytes |
| `dvbridge_metadata.h` | ETSI GS CCM 001 V1.1.1 clauses 6.2/6.3; FFmpeg's LGPL byte-order and CRC utilities; retained public frame-state API | Full payloads, packet arrays, committed frame state and diagnostics compared byte-for-byte with Beta5 |
| `pack_gles300.frag`, metadata-only bodies in `dvbridge_gl_pack.c` | ETSI GS CCM 001 clause 6.4 bit placement, parity scrambling and repetition; retained BT.2020 code-value arithmetic | Full 4K RGBA8 frames compared with separately compiled Beta5 packer, including patch and in-place paths |

The canonical packer uses a four-bit parity table after folding the 12-bit
luma/chroma parity word. Metadata-only writes calculate the parity directly
from stored nibbles. Uniforms, RGBA8 byte order, packet repetition and output
orientation remain unchanged. The GL resource/state adapter, public header,
trivial vertex and generated-source wrapper are original project contributions
covered by the owner's grant. Float conversion constants and operation order
remain a compatibility contract, not a new image-processing algorithm.
Fused renderer/Adaptive shader bodies remain outside this replacement lot.

The serializer constructs the fixed header by field offset, orders extension
descriptors with `qsort` and writes bounded blocks with FFmpeg's big-endian
accessors. FFmpeg's IEEE CRC table supplies the MPEG CRC with the required
initial value and byte order. Known vectors and complete Beta5 packets agree.
The pinned 32-block limit keeps the sort within glibc's stack workspace.
Source/canonical matrices, scene refresh, repeated frames, ID wrapping and L5
placement keep the Beta5 contract. Failed operations produce no valid output;
the existing frame owner commits only successful candidates.

The CM helper expands packed big-endian fields into byte/word transport
fields. It does not implement a display mapper. L3/L4 contain 12-bit fields;
L8 field presence depends on its original block length; L9/L10 custom
primaries are present only with index 255. Reserved bits and trailing padding
retain their Beta5 rejection behavior.

Original extraction hashes and attribution remain in `extraction-origins.json`
and `PROVENANCE.json`. Current replacement hashes are separate overrides in
`owned-sources.json`. The old implementations remain external executable
oracles, with their prior licenses, and are not shipped as replacement code.
This is a documented replacement process, not a claim of legal clean-room work.

References: [libplacebo cache API](https://github.com/haasn/libplacebo/blob/master/src/include/libplacebo/cache.h),
[FFmpeg metadata API](https://github.com/FFmpeg/FFmpeg/blob/n9.0/libavutil/dovi_meta.h),
[MIT dovi_tool syntax](https://github.com/doppingkoala/dovi_tool/tree/d4ad4ba7e6f5acef6c7321dac0139992a082cd8f/dolby_vision/src/rpu/extension_metadata/blocks).
The serializer format is specified by [ETSI GS CCM 001 V1.1.1](https://www.etsi.org/deliver/etsi_gs/CCM/001_099/001/01.01.01_60/gs_ccm001v010101p.pdf).

Reproduce the helper comparison with the same pinned libplacebo in
`PKG_CONFIG_PATH`/the runtime library path:

```sh
python3 CB1/tools/compare_beta5_helpers.py --baseline /path/to/frozen/Beta5/CB1 --ffmpeg-prefix /path/to/matched/ffmpeg
```

The baseline must come from the normal Beta5 commit
`abde400bbf8ef754c971f437dc321bdd03a5986b`. The runner builds separate old/new
programs, compares cache files, validates helper outputs and streams the complete
serializer output/state for exact comparison. It checks baseline helper hashes
and rejects disabled assertions. It does not include
the old GPLv3 implementation in the replacement runtime.

The complete-frame canonical tunnel comparison uses Mesa llvmpipe, not a
mini-PC or physical output:

```sh
python3 CB1/tools/compare_beta5_tunnel.py --baseline /path/to/frozen/Beta5/CB1
```

This compiles the old wrapper with renamed symbols only into a standalone test.
It compares every byte of six 4K input families in both orientations, packet counts
1 through 5, normal packing, metadata-only patching and supported in-place
patching. Finite clipping, near-black, ramps and random colors are included.
The recorded local run compares 1,194,393,600 bytes with zero differences.
This is software-driver evidence, not cross-driver equivalence or a complete
color/patent/certification assessment.

## Remaining scope

Creative adaptations, shared rendering, remaining image transport/packing,
modified libplacebo and Kodi integration still require portion-level review.
Their existing GPLv3 notices remain effective. Upstream FFmpeg and vanilla
LibreELEC dependencies keep their pinned licenses and build configuration.

Offline comparisons do not establish hardware performance or display output
equivalence. No mini-PC or TV is used for this migration stage.
