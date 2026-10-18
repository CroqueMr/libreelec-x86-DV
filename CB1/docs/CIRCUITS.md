# Engine and circuits

Engine: **CB1 0.3**. Each end-to-end rendering circuit has its own version.

| Circuit | Version |
| --- | --- |
| Dolby Vision to Standard Dolby Vision | `CB1-DVDVR.0.3` |
| Dolby Vision Master Reference | `CB1-DVDVMR.0.4` |
| Dolby Vision to HDR10, Reference Basic | `CB1-DVHDR10B.0.3` |
| Dolby Vision to HDR10, Reference Expert | `CB1-DVHDR10X.0.8` |
| Dolby Vision to Dolby Vision Adaptive HDR Mapping | `CB1-DVDVA.0.10` |
| HDR10 to Reference Dolby Vision, AI-assisted | `CB1-HDR10DVR.0.1.2` |
| HDR10 to Dolby Vision Adaptive HDR Mapping, AI-assisted | `CB1-HDR10DVA.0.4` |

Identifiers are defined in `src/cb1_circuit.c`. A circuit revision changes when
its processing contract or rendered result changes. Player UI and driver-only
changes do not require a circuit revision.

Adaptive expands valid L1/L3 scene highlights without requiring creative trims.
Resolved HDR L8 anchors take priority over L2. Trims guide the expansion and remain in the output metadata;
they are not applied twice. Missing or invalid analysis retains the safety path.
It protects blacks and uses a temporal slew limit, with an FP16 reconstruction
intermediate. Curve and metadata calculations retain their existing precision.
The earlier Adaptive A identifier `CB1-DVDVA.0.9` remains an internal comparison
contract, not a separate playback choice.

Standard always uses Fast input-chroma interpolation. Master Reference never
uses it. Auto can switch Master to Standard when presentation headroom is low.
Other CB1 modes follow the Fast setting; Off restores their reference filter.
Transport, GUI and supported FEL upscaling optimizations are automatic.

HDR10 Adaptive uses predicted L1/L3 and a neutral cubic highlight-expansion
curve, without invented creative trims or the authored-DV midtone term. A target
not exceeding the source reference leaves the expansion curve at identity.
Output L1 is measured from the processed image. The inference model and HDR10
Reference AI circuit are unchanged. [Equations](ALGORITHMS.md).

The integration image has an independent release version and records the exact
CB1 source revision. Native HDR10/HLG/SDR and stereoscopic 3D remain player-owned;
they are not CB1 rendering circuits.

[Master Reference](MASTER-REFERENCE.md) defines its admitted representations,
integer reconstruction and deterministic spatial contract. Fast and the saved
FEL scaler preference do not affect this circuit.
