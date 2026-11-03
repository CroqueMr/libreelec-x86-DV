# Engine and circuits

Engine: **CB1 0.5**. Each end-to-end rendering circuit has its own version.

| Circuit | Version |
| --- | --- |
| Dolby Vision to Dolby Vision Reference | `CB1-DVDVR.0.6` |
| Dolby Vision Master Reference | `CB1-DVDVMR.0.6` |
| Dolby Vision Master Reference, IPT-PQc2 output | `CB1-DVDVMRI.0.2` |
| Dolby Vision to HDR10 Rendering | `CB1-DVHDR10B.0.4` |
| Dolby Vision to HDR10 Rendering Reference | `CB1-DVHDR10X.0.12` |
| Dolby Vision to HDR10+ | `CB1-DVHDR10P.0.1` |
| Dolby Vision to Dolby Vision Adaptive HDR Mapping | `CB1-DVDVA.0.11` |
| HDR10 to Dolby Vision Rendering, AI-assisted | `CB1-HDR10DVR.0.1.3` |
| HDR10 to Dolby Vision Adaptive HDR Mapping, AI-assisted | `CB1-HDR10DVA.0.8` |
| HDR10+ to Dolby Vision Rendering, metadata-guided | `CB1-HDR10PDVR.0.2` |

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

Each mode owns one fixed rendering recipe. Reference and conversions retain their
qualified performance filters; Master retains its exact reconstruction. Optional
Master-to-Reference recovery is off by default. Transport, GUI and supported FEL
upscaling optimizations are automatic.

HDR10 Adaptive uses the same scene-guided expansion curve and temporal slew limit as DV Adaptive.
Predicted L1, adjusted by predicted L3, guides the curve without invented creative
trims. Output L1 follows that curve rather than instantaneous frame extrema.
The inference model and HDR10 Reference AI circuit are unchanged.

HDR10+ Dolby Vision Rendering preserves the source picture and uses compatible
single-window MaxSCL and distribution statistics for outgoing descriptive values.
Unavailable statistics are explicitly estimated; usable metadata does not require AI. HDR10+ target
display luminance is not the source peak. Authored tone curves and saturation
adjustments are not translated or applied to pixels. Unsupported source metadata
does not reuse an earlier frame's RPU.

Player information shows the committed AI model version when its prediction is
used, the statistical PQ baseline before inference, generated DV L1/L3 and emitted
L1. These are descriptive values, not authored creative trims. Metadata-only
HDR10+ descriptions do not display a model or a pre-AI baseline.

HDR10 Rendering, HDR10 Rendering Reference and Adaptive process the source-sized picture before final
enlargement. Reconstruction, creative guidance and intermediate precision follow
the circuit policy, not the input dimensions. Adaptive's final enlargement retains
the declared luminance envelope before GUI composition and transport packing.
Reference preserves admitted source-domain transport when fitting smaller or
cropped pictures. Master Reference and the Reference P5 recipe are unchanged.

Input-chroma recipes are shared by Intel and AMD. Intel ADL-N's validated scaler
cache and AMD's eligible presentation-edge rule remain independent backend
optimizations, not user-selectable quality variants.

The integration image has an independent release version and records the exact
CB1 source revision. Standard HDR10/SDR playback remains owned by the player.

[Master Reference](MASTER-REFERENCE.md) defines its admitted representations,
integer reconstruction and deterministic spatial contract. The saved FEL scaler
preference does not affect this circuit.
