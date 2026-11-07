# Blu-ray ISO/menu correction scope

The fixes change Kodi/libbluray's shared reader and navigation paths. They do
not rewrite source ISO files or dispatch by movie name, disc ID or a known
playlist/clip number. A title that reproduced a defect supplies a regression
case; applicability follows the authored events and stream properties.

| Shared behavior | Conditions and regression coverage |
| --- | --- |
| Menu input ownership | HDMV and BD-J plane callbacks; visible/transparent overlays, menu close/reopen, authoritative top-menu events, subtitles kept separate from menus |
| BD-J graphics | Dirty rectangles, crop bounds and image stride, rather than one disc's coordinates |
| Authored stills | Navigation still state drains decoded frames once; ordinary input retry is not treated as a still |
| Chapter and language navigation | Marks at different times sharing a transport packet; keep later authored marks after seeking rather than special-case their indices |
| Clip/angle transitions | Announce navigation boundaries before new transport bytes; preserve normal non-navigation read behavior |
| DV decode preroll | Negotiated client capability plus one HEVC base stream and one HEVC DV stream; retain decode references while suppressing presentation outside authored timestamps, rather than changing every clip |
| Audio/subtitle selection | Keep disc-authored opening selection and retire deselected subtitles; menu overlays remain independent |
| Image root resolution | Local and HTTP/SMB image paths, spaces/escaping and UDF roots; folder/MPLS inputs keep their own path rules |
| Java capability reporting | Report supported stereo capability accurately so discs with an authored fallback can select it; unsupported stereo Java behavior is not emulated |

Behavioral regressions live in `tests/cb1/test_bluray_*.py`,
`test_libbluray_*.py` and `test_bdj_*.py`, using actual patched native source
owners with representative state combinations. The previous ISO campaign's
24 representative qualifications and two tester acceptances keep their
original image scope. A new image's source checks are not a fresh replay of
every disc, branch, bonus, language, BD-Live or stereo configuration.
