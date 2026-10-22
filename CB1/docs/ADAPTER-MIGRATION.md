# Adapter migration status

Local Beta5 source migration. Full-image and hardware qualification remain open.

| Portion | Current decision | Preserved contract |
| --- | --- | --- |
| Kodi `DVBridgeState.cpp/.h` | Replacement GPL-2.0-or-later transaction and property-plan implementation | Public API, capture/rejection decisions, required/optional properties, enum selection, complete stage/restore order, blob ownership and foreign-VSIF rejection |
| libplacebo `9915-hdr10-linear-conversion` additions | Original CB1 contribution under owner's GPL-2.0-or-later grant; upstream LGPL code/notices retained | Patch implementation bytes unchanged; no shader, ABI or default change |
| libplacebo `9916-fel-filter` additions | Original CB1 filter/reference adapter under the same grant; upstream LGPL retained | Patch implementation bytes unchanged; integer-reference shader already retains its LGPL notice |
| libplacebo `9913-processing` | Original ABI/glue GPL-2.0-or-later; replacement lookup/reshape emission LGPL-2.1-or-later | Table dimensions/domains, accumulation order, clipping, null/default behavior and ABI 9 retained; reference code/upstream LGPL unchanged |
| Renderer source-space GUI/fused colour adapter | GPL-2.0-or-later replacement from numerical/alpha contract | Movie values, pair admission, orientation, transfer tables and matrix arithmetic retained; no extra pass or readback |
| DMA-BUF descriptor validation | GPL-2.0-or-later replacement using FFmpeg/libdrm descriptor fields | Same formats, bounds, modifier conditions and cache identities; declared chroma format passed unchanged to EGL |
| Original FEL queue, seek/VPP, metadata mapping and interfaces | Owner's GPL-2.0-or-later grant | Implementation text unchanged; no license change to FFmpeg, libva, EGL or libplacebo |
| Original Kodi bridge, AI source, screenshot, window retirement, menu layout and scaler stub | Owner's GPL-2.0-or-later grant | Ten original project files change notices only; upstream Kodi/Hades-compatible file notices are unchanged |

The output-state replacement implements the existing property contract as
ordered data and a snapshot reader using Kodi/libdrm APIs. Successful capture
publishes owned snapshots only after plane validation. Failure destroys temporary
blobs without changing the captured state. Staging attempts every saved property;
restore uses cloned original blobs. Display matrices, movie samples, transport
payload and driver selection rules are unchanged.

NVIDIA property names, blob types and S31.32 neutral factors are public in the
MIT-licensed [615.71.09 DRM interface](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.71.09/kernel-open/nvidia-drm/nvidia-drm-drv.c)
and [property-state implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.71.09/kernel-open/nvidia-drm/nvidia-drm-crtc.c).
Only the interface contract is consumed; no NVIDIA kernel implementation is copied.
The existing Kodi DRM blob utility and upstream notices are retained.

The prior output adapter was adapted from LibreELEC Hades RC2
`69fc36199f0d5f5d1e5bb4d42f45656e256a6e35`. That historical attribution is not
removed by replacement and does not authorize unrelated Hades code.

## Differential verification

```sh
python3 CB1/tools/compare_beta5_output.py --baseline /path/to/frozen/Beta5/repository
```

The standalone probe compiles the old and new output adapters separately and
compares 195 complete API traces. Cases include both backends, kernel preference,
absent optional/required properties, failed enum/blob/plane queries, owned and
foreign VSIF blobs, partial staging failure, exact restoration and resource cleanup.
A deliberate wrong-enumeration mutation is rejected. Enum names/values, unique
blob identities/payloads and resource creation/destruction are traced separately.
DRM boundary doubles do not qualify a
real driver, HDMI link or GPU. Historical oracle sources are not linked into Kodi.

For the two grant-only libplacebo patches, compare the full patch text from the
first `diff --git` line against normal Beta5. Both are identical; modified-source
hashes of their implementation and processing ABI 9 remain unchanged.

The additional original runtime grants cover `dvbridge_fel.c/.h`,
`dvbridge_fel_seek.h`, `dvbridge_fel_vpp.c/.h`, `dvbridge_placebo.c/.h`, and the
public import/render interfaces. Their implementation text is unchanged. These
are project-specific state, validation and API adapters, not imported decoder,
VPP or colour-mapper implementations. The separate DMA-BUF validator and fused
composition are replacements, not notice-only grants. Historical Hades/YBLOD
attribution remains recorded and does not authorize third-party implementations.

## Dependency qualification

The offline comparisons use a new library built from the published normal-Beta5
libplacebo component archive, SHA-256
`1a42b5d62a3d84740fb3923901f867fc8acc5cd2b3ea08c1b20a780424dbf087`.
This snapshot supplies the frozen library. The candidate is rebuilt separately
with only the `colorspace.c` lookup/reshape replacement. That source hash is
updated to its new implementation; unchanged modified-source locks still match.
The comparison runners load each version's own library, not a shared candidate
library for both sides. No dependency hashes are relaxed.

The canonical patch recipe now includes the paired-row contract-2 reconstruction
and exact MMR table additions already present in the published source snapshot.
All 18 locked libplacebo files and 176 compilation inputs match the qualified
candidate byte-for-byte. No modified-source expectation or upstream pin changed.
CI replays the complete dependency recipe and checks those source locks before
running the integration suite. Complete-image qualification is recorded separately.

Additional differential checks compare 48 complete FP32 processing captures and
24,000 import-layout/normalized identity records. The full-frame composition
probe uses distinct GUI transfer textures and initialized GUI pixels. It rejects
GPU validation failures instead of accepting stale target data. Deliberate GUI
colour, lookup-table and layout mutations are negative controls. Fragment-quad
paths absent on llvmpipe remain unqualified.
