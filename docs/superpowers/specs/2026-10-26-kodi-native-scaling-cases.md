# RC1 Preview G: native Kodi integration case matrix

Specification: [design](2026-10-26-kodi-native-scaling-design.md).
This is the required behavioral and validation scope, not a list of passed
tests. Cases are finite equivalence classes and boundaries; arbitrary dimensions
use the same checked arithmetic, not individual resolution-specific recipes.

## Definitions and authoritative oracle

- **Source**: decoded visible picture, separate from allocated padding and
  chroma-plane sizes. **Output**: settled physical display mode and drawable.
- **1:1**: source crop maps pixel-aligned to the destination with unit scale;
  equal mode names alone do not establish 1:1 with zoom, rotation or anamorphic
  pixels. Borders do not imply scaling.
- **Native oracle**: the pinned Kodi mode finder and settings path with only the
  CB1-specific UHD selection override absent. Keep native whitelist, override,
  refresh matching, default floor, source-size tolerance and display capability
  rules. Do not compare against a simplified hand-written imitation.
- **Admission**: after selection settles, independently validate the actual
  route, transport and target. Pending is not Unsupported. A whitelist is not
  an HDR/DV capability certificate.
- **Pixel promise**: Master reconstruction and metadata are exact before final
  fitting. Unscaled pixel-aligned output retains the frozen exact controls.
  Resized output uses the selected original Kodi filter as its oracle, per the
  user's explicit clarification. It need not match the old CB1 interpolator.
- A "single fit" is one logical spatial operation; separable native filter
  passes can be legitimate. Do not do an extra full-image enlargement and then
  filter it again or shrink it back.

## R: output mode selection and allowed outputs

| ID | Situation | Required result |
|---|---|---|
| R01 | GUI UHD; source 1080p24; adjustment On start/stop; explicit matching 1080p24 entry | Native selector chooses 1080p24; no CB1 UHD override |
| R02 | Same source; selected native target UHD24 | One final enlargement; do not force 1080p because it is the source size |
| R03 | GUI UHD; adjustment Off; a 1080p whitelist entry exists | Preserve the current native output; whitelist does not force an adjustment Kodi has disabled |
| R04 | Actual output 1080p; adjustment Off; UHD source | Keep 1080p and perform one final reduction, subject to route admission |
| R05 | Empty whitelist and GUI UHD | Follow Kodi's native default whitelist/floor; no custom source-resolution policy |
| R06 | Explicit whitelist has several sizes/rates | Match native weighting and tie-breaking; do not sort by largest resolution |
| R07 | Saved native refresh override | Same effect and priority as the native oracle; no bypass in CB1 |
| R08 | 23.976 and 24.000 modes both exist | Preserve native fractional-rate matching; no silent rounding |
| R09 | 29.97/30 source, 59.94/60 output | Expected repeats are not drops; retain native double-rate permission |
| R10 | 24 source, only 60 output, pulldown explicitly permitted | Native 3:2 cadence and permissions; no proprietary timing rule |
| R11 | Stale whitelist entry absent from current EDID/mode list | Ignore/recover as native; do not recreate a nonexistent mode |
| R12 | 4096x2160 desktop or whitelist | Native selection remains authoritative; validate DV for that actual target instead of silently selecting 3840 |
| R13 | 2560x1440 or another real EDID mode | Same selection/admission process; no 1080/UHD-only output list |
| R14 | Modes above 60 Hz or with unsupported route format | Native selection may choose them; do not claim DV supported until its actual transport is qualified; report existing route-policy reason |
| R15 | TV advertises a timing but no DV or no driver DV support | No DV capability inferred from timing; existing route selection and blocking reason |
| R16 | Required HDR10 surface/bit depth unavailable | Existing minimum-10-bit HDR10 admission/chroma policy; never substitute an 8-bit output silently |
| R17 | Native DV uses RGB8 HDMI transport | Preserve packed high-bit-depth payload; do not apply the HDR10 RGB10 rule to tunnel bytes |
| R18 | Display mode/context still changing or 0x0 | Pending; do not allocate a fake 4K target, demote source metadata or persist a failure |
| R19 | User settings include saved per-video mode/filter overrides | Preserve and apply them through native mechanisms; no global preference rewrite |

## G: geometry, dimensions and spatial order

| ID | Situation | Required result |
|---|---|---|
| G01 | 1920x1080 visible to 1920x1080, default view | Pixel-aligned final bypass; no hidden 4K materialization |
| G02 | 1920x1080 to 3840x2160 | Native source-grid treatment; one late enlargement |
| G03 | 2560x1440 to 3840x2160 | Same treatment and adapter as G02, not a third recipe |
| G04 | 2560x1440 to 2560x1440 | Same 1:1 bypass rule |
| G05 | 3840x2160 to 1920x1080 | One late reduction; no 1080 re-expansion before packing |
| G06 | UHD to UHD | Preserve existing fused exact/optimized 4K routes; no new copy or scaler pass |
| G07 | 1536x864 to 2560x1440 | Generic dimensions and checked ratios; no special-case 1080 code |
| G08 | Source 3840x1600 into 3840x2160 | No picture enlargement when width maps 1:1; place borders according to Kodi |
| G09 | Source 1920x800 into 3840x2160 | Display picture 3840x1600 with correct borders in Normal view, not a stretched 3840x2160 image |
| G10 | 1920x1088 allocation, visible 1920x1080 | Use visible crop, not padding, for aspect/analysis/scaler coordinates |
| G11 | 3840x2176 padded decode, visible UHD | Same visible-crop rule; do not mistake allocation padding for an unsupported source |
| G12 | Odd visible source width/height and 4:2:0 | Preserve chroma phase and edge replication; validate transport alignment separately |
| G13 | Fractional crop or fractional destination placement | Honor native sampling phase; do not take an incorrect integer 1:1 shortcut |
| G14 | Anamorphic/non-square pixels | Honor native display aspect and required horizontal resampling |
| G15 | User Zoom, Original Size or Custom view | Use the actual native source/destination rectangles, including clipping/borders |
| G16 | 90/180/270 rotation or GL vertical orientation | Apply orientation once and preserve native geometry; no upside-down output |
| G17 | L5 margins plus Kodi crop/zoom | Keep source metadata coordinates distinct; apply each authorized mapping once, not duplicate crop |
| G18 | Zero/negative/overflowing dimensions, empty visible rect or out-of-bounds target | No submission or stale frame; reject through existing safe failure path with reason |

## F: native filter choice and precise scope

| ID | Situation | Required result |
|---|---|---|
| F01 | Auto, ordinary 1080p enlargement | Preserve native Auto admission, normally bilinear on this pinned renderer |
| F02 | Auto, sub-720p at low frame rate with native HQ support | Preserve native HQ selection; do not redefine all Auto as bilinear |
| F03 | Saved explicit Bilinear | Use native texture interpolation and report it accurately |
| F04 | Saved explicit Lanczos3 optimized | Reuse that actual native kernel, not full Lanczos or a relabeled LP kernel |
| F05 | Saved explicit full Lanczos3 | Reuse that kernel when supported; do not silently substitute optimized for performance |
| F06 | Another native filter supported by this renderer | Preserve its actual native selection; advertise only qualified CB1 handoff support |
| F07 | Saved method unsupported by current renderer/CB1 boundary | Use the native unsupported-method behavior with truthful effective-filter reporting; never claim the requested kernel ran |
| F08 | Genuine 1:1 without fractional placement | Bypass interpolation; do not blur the picture by forcing a convolution shader |
| F09 | Change filter during playback or pause | Apply through a new accepted picture/configuration boundary; no mixed target, stale kernel or duplicate treatment |
| F10 | Switch between Master and another mode | Preserve saved native preference; Master reference contract is not overwritten by a mode change |
| F11 | Native "set as default for all videos" and existing per-file setting | Preserve Kodi persistence precedence; migration does not reset user choices |
| F12 | Load rises while playing | No new custom Fast/Auto quality adaptation; existing explicit Master recovery remains separate |

## D: source formats, processing modes and component domains

| ID | Situation | Required result |
|---|---|---|
| D01 | DV P8.1 Standard | One source-grid reconstruction and native late fit; preserve metadata handling |
| D02 | DV P7 FEL, EL smaller than BL | Existing FEL alignment first, then reconstruction, then final picture fit |
| D03 | DV P7 MEL or inactive residual | No unnecessary FEL enlargement or waiting for a nonexistent active residual |
| D04 | BL1080 + EL540, final1080 | FEL alignment may run; final video enlargement must not run |
| D05 | DV P5 Standard | Preserve direct IPT domain and its established processing; no extra YCbCr/RGB/LMS round trip for the scaler |
| D06 | DV P5 Master | Exact source-grid IPT reconstruction, then the same original Kodi filter; no RGB8 intermediate or added colour conversion |
| D07 | DV Master YCC and existing Master IPT preference | Exact reference reconstruction before native final fitting; unscaled controls remain exact; no silent Standard switch |
| D08 | DV with HLG-compatible base/P8.4 fixture | Preserve source tags and selected route; test where a real fixture exists, never infer from an HDR10 sample |
| D09 | DV Adaptive HDR Mapping | Same algorithm/metadata guidance/black protection/anti-pumping; source stats exclude padding and GUI |
| D10 | DV to HDR10 Basic | Native spatial ownership without re-running native tone mapping or changing the Basic policy |
| D11 | DV to HDR10 Expert | Keep trim domain, TV ceiling, FP precision and final quantization order; no post-pack scale |
| D12 | Existing DV to HDR10+ routes | Preserve the PR's existing metadata algorithms and packet behavior; no new HDR10+-to-DV conversion |
| D13 | HDR10 to DV Reference AI | Preserve model features, source normalization, L1/L3, readiness and existing fallback timing |
| D14 | HDR10 to Adaptive AI | Same spatial contract, source-normalized analysis and original curve; keep active/identity cases distinct |
| D15 | SDR, native HDR10, DV disabled or MVC/3D | Remain on native vanilla/stereo paths; no CB1-specific filter or mode-policy mutation |
| D16 | MKV single-track BL/EL/RPU and ordinary P8/P5 tracks | Same decoded-picture contract and spatial behavior; preserve current layer assembly |
| D17 | MP4 single-track and supported dual-track BL/EL | Preserve stream pairing, timestamps and DV identity before the shared spatial boundary |
| D18 | TS/M2TS with supported separate BL/EL PIDs | Existing assembler remains authoritative; no scaler-specific demux or pairing |
| D19 | Blu-ray ISO/playlist with separate EL, including Gemini Man and 1917 fixtures | Preserve selected playlist, BL/EL synchronization and current DV detection; no spatial fallback masquerading as a successful DV test |
| D20 | ISO via strm/network URL versus an equivalent local input | Same available decoded source yields the same spatial contract; missing layer evidence stays an existing input/admission issue, not forced DV |
| D21 | Start/seek/end or container switch changes decoded crop/size | Reconfigure using actual decoded geometry and existing picture identity, not the filename/container or stale first-frame size |

## T: target, packing, metadata and admission

| ID | Situation | Required result |
|---|---|---|
| T01 | Non-UHD validated DV target | Use actual raster width/height/stride/flip in packing, not source width or constants |
| T02 | Metadata packets cross a raster row boundary | Exact payload/parity/coverage at target stride; no first-pixel stripe or overwritten movie pixels |
| T03 | Metadata capacity/alignment insufficient for a proposed target | Explicit safe admission failure; no truncation or fabricated dimensions |
| T04 | Master without spatial resampling | Complete film carrier and metadata match frozen exact controls; no rounding allowance |
| T05 | Different output resolution | Validate against independent reference geometry/packing oracle, not a checksum from a different resolution |
| T06 | Surface is RGB8 DV tunnel versus HDR10 RGB10/P010/etc | Apply the correct route-specific bit-depth/format contract; no interchange based on texture name |
| T07 | Physical pixels differ from logical GUI grid | Output target and viewport use physical pixels; UI uses native mapping once |
| T08 | Definitive current-mode format/driver rejection | Existing SelectOutput/OutputReason policy, truthful effective route; no hidden 2160p retry |
| T09 | Interlaced/stereo mode selected for a non-stereo CB1 transport | Native timing choice is preserved but ineligible CB1 transport is rejected safely; do not reinterpret it as progressive |
| T10 | New target selected while an old prepared frame exists | Old frame cannot be packed/committed with the new target generation |

## L: lifecycle and transitions

| ID | Situation | Required result |
|---|---|---|
| L01 | Start a movie from a GUI mode of different size/rate | Settle native mode/context before final allocation/packing; retain source identity |
| L02 | Pending GPU preparation while mode changes | Retain resources until last use; no resolve into an incompatible target |
| L03 | Pause/resume with unchanged target/filter | Reuse safe committed frame as native; no repeated processing or metadata drift |
| L04 | Seek forward/back across scene metadata changes | Drain/cancel through existing owner; no stale BL/EL/RPU pairing |
| L05 | Stop during decode/prepare/scale/pack | No use-after-free, hang, crash or loss of return-to-GUI behavior |
| L06 | Switch Standard/Master/Adaptive/conversion while playing | Native context/target transition with matching generations; audio timing remains native |
| L07 | Stop movie A, immediately launch different-size/rate movie B | Reset per-playback pending state; keep saved preferences, no inherited crop/viewport |
| L08 | Hotplug or TV off/on changes EDID/modes | Re-enumerate through native paths; no stale whitelist-derived or global negative capability cache |
| L09 | Portable dual-screen selection, primary display change | Preserve native monitor policy and real selected connector; no new display-selection feature |
| L10 | Imported decoder surface is recycled while final fit pending | Borrowed source lease survives the last real GPU read; no new excessive surface pool |
| L11 | Allocation, shader compilation, import or synchronization failure | Safe cancellation and existing route reason, not stale RGB presentation or a growing retry queue |
| L12 | Reboot/update with saved native filter and resolution settings | Settings survive; capability checks re-evaluate the actual runtime, not test-machine assumptions |

## U: GUI, subtitles, settings and diagnostics

| ID | Situation | Required result |
|---|---|---|
| U01 | GUI/panel over a DV movie | No movie rescale/reconstruction solely because the GUI is visible; preserve transport composition contract |
| U02 | O cycle: Player information, quick switch, video | Same native key flow at every output size; no input deadlock or extra scaler after closing |
| U03 | Subtitle inside or outside L5 active area | Native position/size, readable in borders; no movie crop or subtitle statistic pollution |
| U04 | Scrolling notification or animated GUI | Preserve established full-raster overlay/L5 fix and target lifetime; no film precision loss |
| U05 | Logical1080 GUI on physicalUHD output | No tiny lower-left picture or double scaling of GUI/subtitles |
| U06 | Actual1080 output and mixed GUI assets | Correct layout and viewport, no leftover UHD rectangle or offset |
| U07 | Player information during scaling | Show actual source/target/filter and route; separate final video scaling from FEL scaling |
| U08 | 1:1, copied frame or pending admission | No false Lanczos/scaler-on label and no empty irrelevant processing row |
| U09 | Definitive route failure | Concise blocking reason and actual route; no unconditional unsupported claim from a transient startup state |
| U10 | Repeated identical frames/healthy playback | Transition/error logs only as relevant; no per-frame diagnostic flood or extra full-frame readback |
| U11 | Native screenshot action on SDR/HDR10 and DV routes | Preserve native supported capture and existing explicit DV/Master limitations; do not add readback or alter the transport solely to obtain a screenshot |

## V: fidelity, performance and release gates

| ID | Situation | Required result |
|---|---|---|
| V01 | Master unscaled regressions on both GPUs | Zero changed film pixels/metadata; resized controls use exact source reconstruction followed by the actual Kodi filter |
| V02 | Standard native-filter adoption | Qualify actual native kernel versus old output; do not call different filters bit-identical |
| V03 | 1080p60 compared to the corresponding admitted UHD60 route | No lower cadence or extra unneeded output-size passes; compare effective route, source and target carefully |
| V04 | 1440p/nonstandard dimensions | Same architecture; performance measured, not a separately tuned quality recipe |
| V05 | FEL30 and non-FEL30, no GUI | Zero excess missed presentation intervals beyond expected cadence in qualification windows |
| V06 | 23.976/24/30 source with higher/mismatched refresh | Measure expected native cadence; do not count legitimate repeats as drops or equate refresh rate with movie fps |
| V07 | GUI workloads and unavailable GPU counters | Separate from no-GUI timing; absent counters stay unavailable, not zero |
| V08 | Complete Preview G image and cleanup | Full suites/source receipts/image identity, exact reference checks, post-clean requalification and no failed prototypes left in production |

## Test ownership and execution scope

- Native selection oracle: R01-R19, T08-T10, L01/L08/L09/L12.
- Native spatial/engine GPU witnesses: G01-G18, F01-F12, D01-D14, T01-T07.
- Existing route-policy/metadata and container tests: D01-D21, T02-T06/T08, U03/U04/U09.
- Real interaction and lifetime tests: L01-L12 and U01-U11.
- Paired Intel/AMD runtime qualification and build checks: V01-V08, with actual
  accepted route/admission checked for each cell.

Primary machines remain N100 and Ryzen3 3200U. Retain NVIDIA/other backend
compatibility structurally and through available compile/offline controls; no
runtime NVIDIA or HDR10+ display validation is claimed without hardware.
Record results per case/combination as Pass, Fail, Pending or Hardware-unavailable.
This matrix itself creates no hardware pass result.

Staged qualification uses isolated new-target probes until all reachable routes
have migrated. Global native-selection activation is a separate final gate; a
qualified Standard route alone must not expose an unmigrated Master/AI route to
a non-UHD target.
