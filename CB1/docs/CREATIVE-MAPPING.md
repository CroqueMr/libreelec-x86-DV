# Creative mapping contract

This series separates reconstructed video, creative controls and output transport.
It does not implement or claim the complete licensed Dolby display mapper.

## Metadata operations

| Input | Operation | Domain |
| --- | --- | --- |
| L1 | Consume maximum/average; validate and preserve minimum | Unsigned PQ codes, 0 to 4095; partial numerical coverage |
| L3 | Apply maximum/average offsets once; validate and preserve minimum | Offset code minus 2048; partial numerical coverage |
| L2 target | Select exact, lower/upper, or master-neutral anchor | Interpolate in normalized PQ, not nits |
| L2 slope, offset, power | Decode `code/4096 + 0.5`, `code/4096 - 0.5`, `code/4096 + 0.5` | Neutral code 2048 |
| L2 chroma, saturation | Decode `code/4096 - 0.5` | Neutral code 2048 |
| L2 `ms_weight` | Preserve | No qualified spatial implementation |
| L8 | Resolve typed primary/optional fields and compare parsed/raw values | Independent CM4 scalar/spatial reference; original block length preserved |
| L10 | Resolve and validate custom target bounds/primaries against raw bytes | No guessed unknown IDs or preset overrides |
| L9 | Use Display P3, BT.709, BT.2020 or validated custom mastering primaries | Distinct from BT.2020 transport primaries |

Duplicate anchors and invalid bounds are rejected. Absent trims remain absent.
Optional L8 fields are determined by the raw block length, never zero values.
Present primary, midtone, clipping, saturation and hue groups use masks
1, 2, 4, 8 and 16. Absent parsed defaults are not promoted to present controls.
The CM2.9 compatibility path may consume L2 on a CM4 source, but is labelled
compatibility, not complete CM4 processing. It never adds L8 a second time.

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

## Enhanced control policy

Natural and Signature keep reconstructed pixels, L1/L3, mastering descriptors
and target anchors unchanged. The `cb1-dve-v3` recipe fits the five existing L2/L8
primary controls to fixed goals derived from the unedited authored response in
linear nits. Each change is bounded to 512 codes from its source. Secondary
controls remain unchanged. L2 and L8 are evaluated in their own reference domains
and committed together, or both retained on rejection.

The treatment reference is at least 1000 nits without changing the actual TV
profile or source target descriptions. Natural can remain neutral at a matching
reference. Natural preserves midtones and expands eligible highlights. Signature
raises eligible midtones and applies a stronger bounded color response.
At most 183 evaluations per anchor refine the controls deterministically; repeated
inputs use the existing cache. Black/near-black values, grayscale monotonicity and
authored plateaus are protected. PQ, chroma and hue error ceilings are unchanged.
These controls do not guarantee actual panel luminance or licensed Dolby
equivalence. No metadata blocks, CM version or mastering peak are invented.
No GPU analysis is required for the metadata-first policy.

## Rendering boundary

Expert reconstructs BL and matched applicable EL once. A libplacebo color-map
hook maps to target linear nits, applies the resolved CM2.9 SOP/color controls,
then performs output gamut conversion and PQ encoding. The remaining tone
operation is clip, not a second scene tone map. Neutral/no-anchor controls keep
the previous Expert mapping. L3 changes the effective L1 descriptors once,
including pictures without a trim anchor. Source metadata is never rewritten.

CM4 Expert applies the independent primary, midtone, clipping and secondary
colour controls, with conditional native spatial detail. Enhanced preserves the
pixel reconstruction and edits eligible metadata controls only. Unknown target
descriptions remain unsupported and preserve coherent source metadata. Neither
preset uses panel type to infer display capabilities. The TV retains its TV-Led
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
table dated 2024-02-27, retrieved 2026-10-04. IDs 1, 16, 18, 21, 24, 25, 27,
28, 37, 38, 42, 48 and 49 are explicit entries, not an unknown-ID fallback.
Native libplacebo primaries supply their coordinates and white points.
The public table does not specify preset black levels; `min_pq_present=false`
retains that gap rather than inventing a minimum. Custom L10 retains its
explicit minimum. Manual output retains only the user's peak and gamut.
L10 has no EOTF field; custom transfer remains explicitly unknown.

The structural snapshot selects nearest anchors matching the manual gamut at
signed 16-bit coordinate precision and matching transfer, with a bounded
PQ-distance weight. Known incompatible transfers are excluded; custom targets
retain their unknown transfer without inferring PQ. It does not interpolate or apply
CM4 controls. Unknown descriptions and ambiguous equal-peak anchors have
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
DV Enhanced Natural/Signature use the `cb1-dve-v3` authored-response contract.
Unsupported targets preserve coherent source metadata rather than a partial edit.
These implementations do not establish equivalence to a licensed Dolby mapper.

Retain `LICENSES/GPL-3.0.txt` and the
source links above. These origins do not imply endorsement or certification.
## Independent CM4 numerical reference

The `cb1-cm4-v1` reference uses public IPT/HPE constants from pinned libplacebo
and independent matrix construction. Numerical checks distinguish intentional
processing from quantization error; they do not establish Dolby equivalence.

See [algorithms and metadata](ALGORITHMS.md) for the current equations.
