# Creative mapping contract

This series separates reconstructed video, creative controls and output transport.
It does not implement or claim the complete licensed Dolby display mapper.

## Metadata operations

| Input | Operation | Domain |
| --- | --- | --- |
| L1 | Consume maximum/average; validate and preserve minimum | Unsigned PQ codes, 0 to 4095; partial numerical coverage |
| L3 | Apply maximum/average offsets once; validate and preserve minimum | Decode `(code-2048)/2048` in normalized PQ; quantize effective L1 once |
| L2 target | Select exact, lower/upper, or master-neutral anchor | Interpolate in normalized PQ, not nits |
| L2 slope, offset, power | Decode `code/4096 + 0.5`, `code/4096 - 0.5`, `code/4096 + 0.5` | Neutral code 2048 |
| L2 chroma, saturation | Decode `code/4096 - 0.5` | Neutral code 2048 |
| L2 `ms_weight` | Resolve selected Expert metadata; preserve without execution | Signed sentinel `-1` distinct; no qualified spatial implementation |
| L8 | Resolve typed primary/optional fields and compare parsed/raw values | Independent CM4 scalar/spatial reference; original block length preserved |
| L10 | Resolve and validate custom target bounds/primaries against raw bytes | No guessed unknown IDs or preset overrides |
| L9 | Use Display P3, BT.709, BT.2020 or validated custom mastering primaries | Distinct from BT.2020 transport primaries |

Duplicate anchors and invalid bounds are rejected. Absent trims remain absent.
Optional L8 fields are determined by the raw block length, never zero values.
Present primary, midtone, clipping, saturation and hue groups use masks
1, 2, 4, 8 and 16. Absent parsed defaults are not promoted to present controls.
The CM2.9 compatibility path may consume L2 on a CM4 source, but is labelled
compatibility, not complete CM4 processing. It never adds L8 a second time.

### Expert L2 detail resolution

`creative.l2_detail` retains the real selected L2 anchor codes, target PQs,
their count and the upper PQ-distance weight. Its `level=2` identifies the
metadata provenance; it is not a second creative pass. Other modes leave
this descriptor absent and retain their prior reports and behavior.

`NUMERIC` means that an exact numeric anchor or two numeric bracketing
anchors resolve a code under the independent CB1 interpolation contract.
It does not establish a Dolby spatial strength. `SENTINEL` retains authored
`-1`, never normalized into a negative weight. Mixed contributing sentinel
and numeric anchors remain `UNRESOLVED`. Single-sided numeric anchors are
retained but unresolved; no neutral MS anchor is invented at the master.
Only contributing selected anchors affect the Expert unqualified-detail
reason. No epsilon is added to the existing L2 target selection.

Expert L2 coverage describes the selected plan: bit 5 records detail
present/preserved, while bits 0-4 retain their existing punctual-control
application. `executed=false` and bit 5 never applied accurately report the
missing qualified spatial operator, including a resolved code of 2048.
When L8 supersedes compatibility L2, the renderer still preserves all L2
fields; it does not execute both families. Source metadata stays immutable.

The research syntax check is pinned to quietvoid/dovi_tool
[`614c816b6446dcd1dbaf433403d499a6026fbb5a`, L2](https://github.com/quietvoid/dovi_tool/blob/614c816b6446dcd1dbaf433403d499a6026fbb5a/dolby_vision/src/rpu/extension_metadata/blocks/level2.rs)
and [L8](https://github.com/quietvoid/dovi_tool/blob/614c816b6446dcd1dbaf433403d499a6026fbb5a/dolby_vision/src/rpu/extension_metadata/blocks/level8.rs).
These sources establish signed/unsigned ranges and presence, not complete
mapping equations. Production parser/dependency pins are unchanged.

## Open numerical references

Anchor interpolation follows the public engineering approach in MPC Video
Renderer `DX11VideoProcessor.cpp` at
[`6bb2f3d702993f04e888bf5abd0944a83333b3c5`](https://github.com/Aleksoid1978/VideoRenderer/blob/6bb2f3d702993f04e888bf5abd0944a83333b3c5/Source/DX11VideoProcessor.cpp).
Trim coefficient decoding and the linear-nits SOP/color reference follow
DoViBaker `DoViProcessor.cpp` at
[`ffba39830b694ddca0bf5f73dcf1b462713bb7f4`](https://github.com/erazortt/DoViBaker/blob/ffba39830b694ddca0bf5f73dcf1b462713bb7f4/DoViBaker/DoViProcessor.cpp).
MPC-BE declares GPLv3-or-later in the consulted source headers. DoViBaker
supplies GPLv3 without a separate later-version grant in the consulted files.
The derived creative module, renderer and scalar reference use GPL-3.0-only;
inherited files retain their original terms. The Python reference is separate from runtime C.
These references are experimental open implementations, not proof of Dolby
equivalence. Their different transfer domains must not be mixed silently.

The trim-only reference applies SOP to normalized absolute linear nits, then
the reference color correction, with zero-safe division. Output gamut mapping
is a separate libplacebo operation. A positive source offset may intentionally
lift content black; active-area borders remain signal black.

## Adaptive HDR Mapping control policy

The `cb1-dve-v7` qualification uses the requested display domain and the
existing anchor resolver. It fits one influential existing anchor per family,
including its interpolation weight, without moving target descriptions.
This offline fitter tests a 15% midtone objective without a global saturation
gain. It is not the selected Adaptive pixel-expansion path.

Both families commit coherently or retain the complete source payload.
Unknown targets, zero-influence anchors and failed fits do not count as
enhancement. Existing numerical guards remain unchanged, and a nonidentity
candidate must significantly reduce objective error. The stronger expansion
is not yet qualified on the tested neutral fixtures.

See [algorithms](ALGORITHMS.md) for equations, reference domains and acceptance
criteria. The reference is not a complete TV mapper or a panel measurement.

## Rendering boundary

Expert reconstructs BL and matched applicable EL once. A libplacebo color-map
hook maps to target linear nits, applies the resolved CM2.9 SOP/color controls,
then performs output gamut conversion and PQ encoding. The remaining tone
operation is clip, not a second scene tone map. Neutral/no-anchor controls keep
the previous Expert mapping. L3 changes the effective L1 descriptors once,
including pictures without a trim anchor. Source metadata is never rewritten.

CM4 Expert applies the independent primary, midtone and clipping controls,
with conditional native spatial detail. SDR-only six-vector hue/saturation
trims are preserved, not executed in HDR10. Adaptive HDR Mapping
expands reconstructed pixels using the original metadata and emits consistent
output descriptors. Unknown target descriptions remain unsupported and preserve
coherent source metadata. Panel type does not infer display capabilities. The TV retains its TV-Led
display mapping; this is not the licensed Dolby display mapper.

## Adaptation record

| Origin | Use in this series | Destination |
| --- | --- | --- |
| DoViBaker, erazortt and contributors, revision above | Adapt coefficient decoding and linear-nits SOP/color equations; no decoder or three-point display mapper copied | `dvbridge_creative.c`, creative shader in `dvbridge_render.c`, Python scalar reference |
| MPC-BE / MPC Video Renderer contributors, (C) 2018-2026 see Authors.txt | Adapt PQ anchor interpolation; do not reuse its PQ-domain shader as a linear-domain shader | `dvbridge_creative.c`, Python anchor reference |
| dovi_tool contributors, `d4ad4ba7`, MIT | Public L9 primary-index table and existing raw CM grammar | L9 resolution; inherited MIT notice retained |

## CM4 structural targets and numerical gate

CM4 syntax is pinned to doppingkoala/dovi_tool
[`d4ad4ba7e6f5acef6c7321dac0139992a082cd8f`](https://github.com/doppingkoala/dovi_tool/tree/d4ad4ba7e6f5acef6c7321dac0139992a082cd8f).
The existing transport helper is reused unchanged. New parsed/raw consistency
checks use the matched FFmpeg producer in `config/dependencies.json`. Custom
primary coordinates must match its signed 16-bit / 32767 rational description.
No implementation code is copied from a proprietary component.

Preset peak/gamut/EOTF descriptions follow the public Dolby
[Mastering and Target Displays](https://professionalsupport.dolby.com/s/article/Mastering-and-Target-Displays?language=en_US)
table dated 2024-02-27, retrieved 2026-10-04. IDs 1, 16, 18, 21, 27,
28, 37, 38, 42, 48 and 49 are explicit entries, not an unknown-ID fallback.
Native libplacebo primaries supply their coordinates and white points.
The public table does not specify preset black levels; `min_pq_present=false`
retains that gap rather than inventing a minimum. Custom L10 retains its
explicit minimum. Manual output retains only the user's peak and gamut.
L10 has no EOTF field; custom transfer remains explicitly unknown.
IDs 24 and 25 are custom targets, not reserved presets. Their L10 descriptors
must pass the same raw/parsed bounds and primaries validation as other custom targets.

The target resolver selects nearest anchors matching the manual gamut at
signed 16-bit coordinate precision and matching transfer, with a bounded
PQ-distance weight. Known incompatible transfers are excluded; custom targets
retain their unknown transfer without inferring PQ. Expert interpolates decoded
CM4 coefficients between eligible anchors. Unknown descriptions are skipped in
Expert when other eligible anchors remain. Ambiguous equal-peak anchors have
separate statuses and no selected controls. Ambiguity is evaluated at the final
nearest peaks, independently of metadata block order. Preset L10 overrides, invalid PQ
ordering, duplicate IDs and contradictions with parsed fields are rejected.

Grammar and neutral codes alone do not establish a licensed domain/order for
L8 midtone, clipping, secondary hue/saturation or spatial detail. The audited
DoViBaker reference processes L2, not these complete CM4 operations. The
[Autodesk trim guide](https://help.autodesk.com/cloudhelp/2022/ENU/Flame-HDR/files/create-hdr-content/Flame_HDR_create_hdr_content_apply_creative_trims_html.html)
describes creative intent, not a complete numerical mapper. Independent CM4
reference outputs and tolerances qualify this project's numerical contract only.

HDR10 Expert implements the independent CM4 scalar/spatial reference.
Dolby Vision Adaptive HDR Mapping uses `cb1-dve-pixel-v1`; the older `cb1-dve-v7`
fitter remains an offline numerical reference, not the selected playback path.
Unsupported guidance preserves a coherent native pair rather than a partial edit.
These implementations do not establish equivalence to a licensed Dolby mapper.

Retain `LICENSES/GPL-3.0.txt` and the
source links above. These origins do not imply endorsement or certification.

## Independent CM4 numerical reference

The `cb1-cm4-v1` reference uses public IPT/HPE constants from pinned libplacebo
and independent matrix construction. Numerical checks distinguish intentional
processing from quantization error; they do not establish Dolby equivalence.

See [algorithms and metadata](ALGORITHMS.md) for the current equations.

Expert missing, zero or inconsistent L1/L3 statistics use valid source static
luminance descriptors. Source metadata remains unchanged and image samples are
not forced to black. Structural/raw corruption remains invalid. This admission
change is confined to Expert.

The Dolby [trim-controls guide](https://professionalsupport.dolby.com/s/article/The-Dolby-Vision-Trim-Controls)
limits secondary six-vector trims to SDR generation. Expert preserves their
presence and raw values but does not execute them in HDR10. Generic offline
operators and Adaptive guidance retain their existing behavior.
