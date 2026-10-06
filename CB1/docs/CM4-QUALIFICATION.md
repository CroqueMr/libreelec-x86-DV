# CM4 processing scope

HDR10 Expert uses the independent `cb1-cm4-v1` operator. Authored-DV Enhanced
uses `cb1-dve-v3`, preserving reconstructed pixels and coherently editing
eligible existing primary controls.

| Operation | Processing |
| --- | --- |
| L8 primary and optional fields | Resolve raw/parsed values with explicit presence |
| L10 target descriptions | Validate bounds, primaries and target identity |
| Midtone and highlight controls | Independent Expert operator |
| Six-color hue/saturation | Independent IPT/PQ operator |
| Spatial detail | Conditional native libplacebo path |
| Enhanced Natural / Signature | Bounded primary-control fit with source preservation |

Unknown targets and contradictory fields are not replaced with invented
defaults. L2 compatibility and L8 are not stacked. Optional absent controls
remain absent.

Automated checks cover metadata consistency and the independent numerical
contract. They do not establish proprietary-mapper equivalence or universal
hardware compatibility.

See [algorithms](ALGORITHMS.md), [source attribution](CREATIVE-MAPPING.md) and
[adapter contract](CREATIVE-INTEGRATION.md).
