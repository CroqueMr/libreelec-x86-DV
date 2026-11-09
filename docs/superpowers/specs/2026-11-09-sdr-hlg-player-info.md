# SDR, HLG and Player information

Approved by the user, 2026-11-09. Implement through verification and the normal preview build. No Astra and no Support build. Base: f630d2e9eaabc3b83d27621b64af044e7a316f4d (RC4 Preview Update 2).

## Processing

Add SDR Rendering for HDR10/HDR10+ and Dolby Vision. Dolby Vision reconstructs the original BL, applicable EL/FEL and RPU before tone/gamut mapping. Share the existing libplacebo renderer, import, spatial fitting, picture identity, retirement and presentation owners. No parallel pipeline or silent FEL discard.

SDR uses BT.709 and a separate saved profile: Reference 100 nits/gamma 2.4; Bright room 200 nits/gamma 2.2; Custom/Projector configurable peak, gamma and black floor. These are rendering targets, not measured display brightness. SDR removes DV/HDR10/HDR10+ signaling and attests the actually accepted output; an SDR-only sink must not require HDR/DV transport. Use available native depth and proper dithering.

Add plain-HLG to Dolby Vision Rendering (AI), analogous to the existing HDR10 DV Reference circuit, using reference HLG normalization before shared analysis. HLG has ONLY DV Reference and Kodi default, no Adaptive and no HDR conversion. Preserve native Kodi HLG. Distinguish HLG-base Dolby Vision P8.4/P10.4 carrying RPU from plain HLG. Never invent authored L2/L8. Preserve independent source preferences; fallback never overwrites them.

Integrate settings, quick switch, availability/reasons, paused/live changes, lifecycle and committed telemetry with existing modes.

## Player information

Integrate and correct PR92 against this base. Keep Input / Processing / Output. Input describes the original file including metadata not applied. Processing contains only actually applied blocks (no grey unused blocks). Output describes the accepted signal and forwarded metadata, including forwarded trims. Use the same metadata order L1 through L255 everywhere. Never wrap a field onto two lines. The user's physical review rejects automatic scrolling: use static short labels, and provide full long values through a manually opened details view. Hide empty sections. Keep pending/unknown/fallback distinct from effective output. Preserve native Kodi information without CB1. Audit PR source snapshot and FEL/MEL reset fixes rather than applying stale patches blindly.

## Qualification

Tests cover SDR/HDR/HLG/DV capability combinations, P5/P7 MEL/FEL/P8/P10, ST/DT and HDR10+, corrupt/missing metadata, overlays, seek, source/mode changes and stop/reopen. Run matched native source replay and full tests, build the normal preview, inspect actual payloads and qualify available physical hardware without claiming unavailable GPU tests. Preserve all existing RC4/Xe3/NVIDIA/CEC/ISO/logger fixes. No modifications to synced sources or main branch.
