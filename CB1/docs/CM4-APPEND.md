# Optional CM4 metadata

Player > Videos > CB1, Advanced level. Off by default. The connected circuits
are authored DV Reference and Master Reference, including the IPT output.
They append metadata after reconstruction. The offline LLDV engine also uses
the options for its local display mapping.

| Choice | Append condition on original source metadata |
| --- | --- |
| Off | Never |
| CM2.9 without L2 trims | No L2 present |
| Always | Source is not already CM4 |
| Auto | No L2, or mastering peak meets the selected trigger |
| Auto 2 | No L2, or L1 max is within TV peak plus the chosen headroom |

Auto's Source trigger compares TV peak against mastering peak. Fixed triggers
are 1000, 2000, 4000 and 10000 nits. Auto 2 headroom is 0..50%, default 20%.
Auto 2 with L2 requires a valid TV peak; like CE, absent L1 qualifies when that
peak is known. A missing TV peak leaves original metadata in place and is logged.
The Auto trigger uses rounded whole-nit mastering brightness; Auto 2 compares
12-bit PQ codes against the rounded ST2084 threshold. CE's nominal source codes
3079/3388/3696/4095 resolve to 1000/2000/4000/10000 nits; source codes below
2055 use CE's 96-nit floor for this decision only, not for pixel processing.

Added defaults match avdvplus/libdovi: neutral L3 offsets (2048 each), L9
P3-D65, L11 cinema/D65 and L254 version index 2. P3-D65 is an explicit default,
not a new measurement of the mastering display. Existing CM4 blocks are not
replaced, and L2 blocks are not translated into L8.

Disable L2 trims is independent. The append decision always uses original L2
presence, before an output copy removes L2. L8 and the reconstruction input
remain untouched. Enabling either setting deliberately modifies Master output
metadata; disable both for the original reference output.

For the connected TV-led circuits, only dynamic metadata changes, with no new
pixel pass, queue or HDMI modeset. Output changes take effect on the next
prepared frame. Player information keeps source classification unchanged and
reports appended blocks only after the
corresponding output frame is committed. Transition diagnostics are rate-limited.
The TV's visual response, including Auto 2 threshold transitions, requires
physical display qualification; adding CM4 is not a recovered CM4 grading.

If optional CM4 cannot fit the validated wire payload, the same circuit keeps
the original metadata and logs result 6 (rejected). Explicit L2 removal remains
independent. Malformed original input is never made eligible by either option.
Diagnostic result codes: 0 off, 1 existing CM4, 2 not selected, 3 missing TV peak,
4 appended, 5 invalid configuration/input, 6 optional append rejected.

## Offline LLDV

The player-led mapper uses the same decisions with its configured target peak
and resolves a temporary copy. Neutral L3 leaves L1 values intact. The default
P3-D65 L9 can affect gamut mapping. Existing CM4 takes precedence and legacy
L2 remains usable unless explicitly disabled. The original metadata drives
BL/EL reconstruction and supplies the source identity in the result. The
offline result exposes the decision in `applied.cmv40_status`. L8 can only come
from the source.
