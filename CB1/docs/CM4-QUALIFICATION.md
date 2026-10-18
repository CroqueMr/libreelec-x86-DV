# CM4 processing scope

HDR10 Expert uses the independent `cb1-cm4-v1` operator. Authored-Dolby Vision Adaptive HDR Mapping
uses `cb1-dve-pixel-v1` for trim-guided expansion and fresh output analysis.
The old `cb1-dve-v7` fitter remains a separate offline reference.

| Operation | Processing |
| --- | --- |
| L8 primary and optional fields | Resolve raw/parsed values with explicit presence |
| L10 target descriptions | Validate bounds, primaries and target identity |
| Midtone and highlight controls | Independent Expert operator |
| Six-color hue/saturation | Generic offline IPT/PQ operator; preserved, not executed in HDR10 Expert |
| L8 spatial detail | Conditional native libplacebo path, independent strength conversion |
| L2 spatial detail | Selected Expert raw/PQ resolution; preserved, not executed |
| Adaptive HDR Mapping | Metadata-guided pixel expansion; scene-curve L1 and output L5 |

Unknown targets and contradictory fields are not replaced with invented
defaults. Expert retains valid anchors alongside an unrelated unknown target.
L2 compatibility and L8 are not stacked. Optional absent controls
remain absent.

Expert missing/unusable L1 uses valid static source descriptors, without
changing the requested display reference or rewriting source metadata. This
does not reconstruct missing analysis. Structural corruption remains rejected.

Expert now distinguishes selected L2 detail presence, numeric resolution,
sentinel `-1`, unresolved endpoints and actual execution. An unrelated L2
anchor cannot trigger a selected-detail warning. The five existing punctual
controls and the independent L8 scalar/spatial equations remain unchanged.
No L8 `.30` strength conversion is copied into L2 and no synthetic detail
command is supplied at the master. A resolved numeric code is not a
qualified spatial operator; L2 detail remains unexecuted and preserved.

External qualification still requires raw HDR reference output with a pinned
mapper version, target, gamut, range and encoding. Internal scalar/GPU
agreement does not demonstrate Dolby/CoreELEC equivalence, and syntax or a
mastering application's default values cannot supply the missing equations.

Automated checks cover metadata consistency and the independent numerical
contract. They do not establish proprietary-mapper equivalence or universal
hardware compatibility.

See [algorithms](ALGORITHMS.md), [source attribution](CREATIVE-MAPPING.md) and
[adapter contract](CREATIVE-INTEGRATION.md).
