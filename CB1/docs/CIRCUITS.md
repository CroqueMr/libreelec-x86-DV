# Engine and circuits

Engine: **CB1 0.3**. Each end-to-end rendering circuit has its own version.

| Circuit | Version |
| --- | --- |
| Dolby Vision to Standard Dolby Vision | `CB1-DVDVR.0.5` |
| Dolby Vision Master Reference | `CB1-DVDVMR.0.5` |
| Dolby Vision to HDR10, Reference Basic | `CB1-DVHDR10B.0.4` |
| Dolby Vision to HDR10, Reference Expert | `CB1-DVHDR10X.0.10` |
| Dolby Vision to Dolby Vision Adaptive HDR Mapping | `CB1-DVDVA.0.11` |
| HDR10 to Reference Dolby Vision, AI-assisted | `CB1-HDR10DVR.0.1.3` |
| HDR10 to Dolby Vision Adaptive HDR Mapping, AI-assisted | `CB1-HDR10DVA.0.7` |

Identifiers are defined in `src/cb1_circuit.c`. A circuit revision changes when
its processing contract or rendered result changes. Player UI and driver-only
changes do not require a circuit revision.

Adaptive expands valid L1/L3
scene highlights without requiring creative trims. Resolved HDR L8 anchors take
priority over L2. Trims guide the expansion and remain in the output metadata;
they are not applied twice. Missing or invalid analysis retains the safety path.
The circuit protects blacks and uses the existing temporal slew limit.
It uses an FP16 reconstruction intermediate; the curve and metadata model retain
their existing precision.

Each mode owns one fixed rendering recipe. Standard and conversions retain their
qualified performance filters; Master retains its exact reconstruction. Optional
Master-to-Standard recovery is off by default. Transport, GUI and supported FEL
upscaling optimizations are automatic.

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

Input-chroma recipes are shared by Intel and AMD. Intel ADL-N's validated scaler
cache and AMD's eligible presentation-edge rule remain independent backend
optimizations, not user-selectable quality variants.

The integration image has an independent release version and records the exact
CB1 source revision. Standard HDR10/SDR playback remains owned by the player.

[Master Reference](MASTER-REFERENCE.md) defines its admitted representations,
integer reconstruction and deterministic spatial contract. The saved FEL scaler
preference does not affect this circuit.
