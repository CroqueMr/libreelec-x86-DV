# Engine and circuits

Engine: **CB1 0.3**. Each end-to-end rendering circuit has its own version.

| Circuit | Version |
| --- | --- |
| Dolby Vision to Standard Dolby Vision | `CB1-DVDVR.0.5` |
| Dolby Vision Master Reference | `CB1-DVDVMR.0.5` |
| Dolby Vision to HDR10, Reference Basic | `CB1-DVHDR10B.0.4` |
| Dolby Vision to HDR10, Reference Expert | `CB1-DVHDR10X.0.9` |
| Dolby Vision to Dolby Vision Adaptive HDR Mapping (A) | `CB1-DVDVA.0.9` |
| Dolby Vision to Dolby Vision Adaptive HDR Mapping (B) | `CB1-DVDVA.0.11` |
| HDR10 to Reference Dolby Vision, AI-assisted | `CB1-HDR10DVR.0.1.2` |
| HDR10 to Dolby Vision Adaptive HDR Mapping, AI-assisted | `CB1-HDR10DVA.0.5` |

Identifiers are defined in `src/cb1_circuit.c`. A circuit revision changes when
its processing contract or rendered result changes. Player UI and driver-only
changes do not require a circuit revision.

Adaptive A retains its existing FP32 response. Adaptive B expands valid L1/L3
scene highlights without requiring creative trims. Resolved HDR L8 anchors take
priority over L2. Trims guide the expansion and remain in the output metadata;
they are not applied twice. Missing or invalid analysis retains the safety path.
Both variants protect blacks and use the existing temporal slew limit.
B uses an FP16 reconstruction intermediate; the curve and metadata model retain
their existing precision.

Standard always uses Fast input-chroma interpolation. Master Reference never
uses it. Auto can switch Master to Standard when presentation headroom is low.
Other CB1 modes follow the Fast setting; Off restores their reference filter.
Transport, GUI and supported FEL upscaling optimizations are automatic.

HDR10 Adaptive uses the same scene expansion and temporal slew limit as Adaptive B.
Predicted L1, adjusted by predicted L3, guides the curve without invented creative
trims. Output L1 follows that curve rather than instantaneous frame extrema.
The inference model and HDR10 Reference AI circuit are unchanged.

Basic, Expert and Adaptive process the source-sized picture before final
enlargement. Reconstruction, creative guidance and intermediate precision follow
the circuit policy, not the input dimensions. Adaptive's final enlargement retains
the declared luminance envelope before GUI composition and transport packing.
Standard preserves admitted source-domain transport when fitting smaller or
cropped pictures. Master Reference and the Standard P5 recipe are unchanged.

Fast chroma interpolation is shared by Intel and AMD. Intel ADL-N's validated
scaler cache and AMD's eligible presentation-edge rule are independent backend
optimizations, not separate Fast picture filters.

The integration image has an independent release version and records the exact
CB1 source revision. Standard HDR10/SDR playback remains owned by the player.

[Master Reference](MASTER-REFERENCE.md) defines its admitted representations,
integer reconstruction and deterministic spatial contract. Fast and the saved
FEL scaler preference do not affect this circuit.
