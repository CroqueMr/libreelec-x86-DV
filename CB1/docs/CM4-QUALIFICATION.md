# CM4 processing scope

The independent `cb1-cm4-v1` scalar/spatial operator is a numerical reference,
not the complete **LLDV Reference – HDR10 Output** runtime. That runtime uses
explicit player-led PQ mapping and available L2 compatibility; it does not stack
L3 or a full L8 creative pass onto the curve. L8 spatial and secondary controls
remain unexecuted. [Current runtime contract](ALGORITHMS.md#dolby-vision-to-lldv-reference--hdr10-output).

Authored-Dolby Vision Adaptive HDR Mapping uses `cb1-dve-pixel-v1` for trim-guided
expansion and scene-curve output metadata. Compatible L8 anchors take precedence
over L2; no missing creative controls are invented. The old `cb1-dve-v7` fitter
remains a separate offline reference.

Raw/parsed L8 presence, L10 targets, primaries and metadata contradictions are
validated independently. Unknown targets do not become invented default displays.
L2 and L8 are not stacked as two creative grades.

External qualification requires raw reference output with a pinned mapper,
target, gamut, range and encoding. Internal scalar/GPU agreement does not establish
Dolby/CoreELEC equivalence, and a mastering application's defaults cannot supply
missing equations. Automated checks do not prove universal hardware compatibility.

See [algorithms](ALGORITHMS.md), [source attribution](CREATIVE-MAPPING.md) and
[adapter contract](CREATIVE-INTEGRATION.md).
