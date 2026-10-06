# Engine and circuits

Engine: **CB1 0.1**. Each end-to-end rendering circuit has its own version.

| Circuit | Version |
| --- | --- |
| Dolby Vision to Standard Dolby Vision | `CB1-DVDVR.0.1` |
| Dolby Vision to HDR10, Reference Basic | `CB1-DVHDR10B.0.1` |
| Dolby Vision to HDR10, Reference Expert | `CB1-DVHDR10X.0.3` |
| Dolby Vision to Enhanced Dolby Vision, Natural | `CB1-DVDVEa.0.3` |
| Dolby Vision to Enhanced Dolby Vision, Signature | `CB1-DVDVEb.0.3` |
| HDR10 to Reference Dolby Vision, AI-assisted | `CB1-HDR10DVR.0.1.1` |
| HDR10 to Enhanced Dolby Vision, Natural, AI-assisted | `CB1-HDR10DVEa.0.1.1` |
| HDR10 to Enhanced Dolby Vision, Signature, AI-assisted | `CB1-HDR10DVEb.0.1.1` |

Identifiers are defined in `src/cb1_circuit.c`. A circuit revision changes when
its processing contract or rendered result changes. Player UI and driver-only
changes do not require a circuit revision.

The integration image has an independent release version and records the exact
CB1 source revision. Standard HDR10/SDR playback remains owned by the player.
