# CB1 numerical contracts

Status: Task 6A offline image composition and state contract reviewed and
sponsor-approved. Task 6B experimental transformed TV-Led contract is declared,
pending independent numerical review. No renderer is
enabled by these tests. Runtime, compiled GPU qualification and hardware
acceptance remain separate gates.

`tests/reference/operation-matrix.json` distinguishes ready scalar/discrete and image
reference contracts, and historical creative
operations explicitly not applied in Expert or Enhanced DV. Native and Basic
are unchanged. Task 6B below owns transformed TV-Led metadata.

## Transformed TV-Led experiment, Task 6B

This separately qualified output is `CB1_ETSI_LEGACY_LITERAL`, not newly
qualified Dolby CM2.9 analysis, CM4 creative re-authoring or complete ST
Application #1 conformance. The sponsor accepted literal equality-capable
legacy carriage with receiver qualification still required. Original CM2.9
and CM4 bytes, generation, source mastering/L1 and reconstruction inputs
remain immutable. Standard still transmits original metadata. Enhanced DV
does not bypass the television mapper, change TV-Led signaling or request
disabled TV tone mapping. No LLDV behavior is introduced.

### Image and active window

Use the approved Task 6A reconstruction, full FEL, complete scaler, source
scene proxy, spline/IPT/perceptual mapping, Natural/Intense and nominal-to-
BT2020 conversion unchanged, with the coordinator-approved shared Enhanced
entrance projection documented below. Both formats share that algorithm. The analysis
image is absolute BT2020/PQ after enhancement/container encoding and before
GUI, subtitles, final orientation, quantization and transport packing.
Neither source L1 nor source mastering is updated from this output analysis.
Absent/invalid essential source L1 or source reconstruction still fails.

One explicit format difference closes the fractional-border mismatch:
Enhanced DV uses the existing positive `lround` source-margin-to-final-L5
rule for final borders as well as analysis. Source geometry and L5 are not
mutated. For source dimensions sw,sh, destination x,y,dw,dh, margins l,r,t,b:

`L=x+floor(l*dw/sw+.5)`, `R=3840-x-dw+floor(r*dw/sw+.5)`,
`T=y+floor(t*dh/sh+.5)`, `B=2160-y-dh+floor(b*dh/sh+.5)`.

The integer active window is `[L,3840-R) x [T,2160-B)`. Exactly its pixels
are analyzed and exactly its complement is signal black before GUI. Retain
the existing positive dimensions, fit/aspect and even destination x/dw
checks. Empty/invalid windows fail, never repair. Absent source L5 uses zero
source margins, not invented statistics. HDR10's fractional pixel-center
mask and Standard's existing normalization are unchanged. At a .5 left/top
boundary DV excludes the previous pixel even though the HDR10 center rule
can include it. Each side, odd windows, absent L5 and downscaling have frozen
controls. No additional source crop is authorized.

### Named output analysis

`BT2020_LINEAR_2X2_MAXRGB_PQ_FRAME` is the sole output analyzer. Decode each
finite PQ component in [0,1] using absolute ST2084 referenced to 10000 nits.
Anchor nonoverlapping 2x2 groups at the active upper-left. Average linear
components within each group; partial right/bottom groups average only their
in-window pixels. Every group has one equal statistical weight, not its
pixel count. Encode the largest averaged RGB component with PQ. Then take
minimum, arithmetic mean of these PQ samples, and maximum for this frame.
Exact signal zero stays zero. Reject invalid/nonfinite/out-of-domain images,
not concealed clipping. No CIE-Y, LMS, peak detector, smoothing, percentile,
shot prediction, PQ-component averaging, mean nits or mean integer codes.

The reduced maxRGB domain follows the public field correspondence in
[ETSI CCM 001, 6.2.2](https://www.etsi.org/deliver/etsi_gs/CCM/001_099/001/01.01.01_60/gs_ccm001v010101p.pdf)
and [ST 2094-10, 6.1.2-6.1.5](https://pub.smpte.org/doc/st2094-10/20160518-pub/st2094-10-2016.pdf).
BT2020 linear reduction, partial edges and frame lifetime are explicit CB
policy choices for its known output, not a Dolby LMS analyzer equivalence.
Five-place positive half-up rounding is `floor(s*100000+.5)/100000`, monotone
for nonnegative statistics. Then `Q(s)=min(4095,floor(4096*s+.5))`.
Five-place rounding is an own reproducibility policy. The factor 4096 is the
carriage convention, distinct from the pinned source reader's 4095 division.
Store L1 in min,max,avg order. `.6` codes 2458; full scale codes 4095.

True black/gray/white and statistic-precision degeneracy keep equal statistics
and equal codes, with no floor, epsilon, neighboring metadata or CM4 offsets.
Unequal normalized values can also collide at 12 bits. This wire grammar is
representable and accepted by the current CPU serializer, but equality does
not satisfy ST 6.1.9's strict adjusted normalized ordering with zero offsets.
The claim is deliberately legacy carriage, not complete Application #1.
Receiver tests must include black, constants at several levels, nonuniform
equal-maxRGB, five-place degeneracy and ordinary 12-bit collisions.

### Output descriptors and block policy

Author a synthetic nominal regrade envelope, not source mastering provenance
or a measured television. Maximum nominal nits is ceil(requested double peak),
minimum signal is zero. `source_min_PQ=0`; `source_max_PQ=Q(idealPQ(ceil(peak)))`
without intermediate five-place rounding. This field describes the newly
authored image's nominal envelope, never L1 maximum or actual TV peak. The
envelope permits below-envelope images and does not force their maximum.
Selected gamut remains policy intent; the actual container/transport color
interpretation is BT2020/PQ. No source L9 or custom L10 measurement is invented.
Panel type creates no measured black/contrast. Unknown output program-wide
MaxCLL/MaxFALL signal zero with measured=false and are not transmitted as L6.

Descriptor quantization has <=1/8192 normalized-PQ error except endpoint
saturation, whose endpoint error is 1/4096. Decoding code/4096 is quantized
information, not exact nits. Ceil increases nominal envelope by <1 nit; it
does not add physical calibration precision. Frozen independent boundaries:
1000.25 ->1001 ->PQ .7519360516806833 ->3080;
1500 ->PQ .7960589072078613 ->3261;
1500.000001 ->1501 ->PQ .7961316169134083 ->3261;
10000 ->1 ->4095. A near-sentinel descriptor-only probe rounds to 1 nominal
nit; it is not a successful image treatment. Task 6A capability rejection and
collapsed public PQ range remain unchanged.

| Input/field | Transformed output disposition |
| --- | --- |
| Mapping, NLQ, pivots, source matrices, full FEL | Retain immutable reconstruction inputs only; never feed output metadata back to reconstruction. |
| Signal fields/matrices | Derive established PQ/12-bit/YCbCr/4:2:2/full-range transport; fixed existing BT2020 coefficients. |
| DM ID, diagonal | Retain established transport constants 0 and 42, not measured panel geometry. |
| Source mastering PQ | Retain original provenance separately; derive the explicit nominal regrade envelope on output. |
| L1 | Derive exactly one literal frame analysis in min,max,avg 12-bit code order. Source L1 stays untouched. |
| L5 | Derive exactly one final integer active area shared by video mask and analyzer. Four unsigned 12-bit margin fields. |
| L2 | Remove from deliberately authored trim-free legacy output; original target-trim intent is relinquished, not preserved or neutralized. |
| L4 | Remove unqualified optional temporal anchors; no new temporal policy. |
| L3, L8, L9, L10, L11, L254 | Remove as CM4-generation-inapplicable. No neutral CM4 block or compatibility L2 authoring claim. |
| L6 | Retain source provenance only; not transmitted, not relabeled measured output CLL/FALL. |
| L255, unknown output levels | Unsupported, not raw copied. Source provenance remains separate; output requests fail instead of silently adding such levels. |

Legal output presence is precisely L1 then L5, no CM4 marker. Optional source
trim absence is legal; essential source eligibility still comes from Task 6A.
This is a positive authored policy with new statistics/descriptors/geometry,
not source-L1 copying plus trim deletion presented as validation.

### Existing CPU packet implementation and revision refresh

Reuse the CPU serializer and fixed packer, not GPU packet construction. Legacy
payload has 71 header bytes, 11-byte L1 and 13-byte L5: exactly 95 bytes and one
128-byte packet. Header DM=0; PQ=65535, zero EOTF parameters, depth/space/chroma/
range bytes=12,0,1,1; diagonal=42; block count=2. L1 has big-endian length6,
level1 then min,max,avg u16; L5 length8,level5 then L,R,T,B u16. Fixed matrices
and offsets are unchanged from `dvbridge_metadata.h`. Packet begins 0,id*17,0,
big-endian length95; payload starts byte5; zero pad through byte123. CRC is the
existing non-reflected polynomial 0x04c11db7, initial0xffffffff, no final xor,
stored big-endian at124..127. ID advances modulo16 only on payload byte change,
not merely because an identity changes; first/reset ID=0. No new framing.

Proposed smallest serializer extension, declarations only:

```c
struct dvbridge_candidate *dvbridge_prepare_output(
    const struct dvbridge_context *context, const void *output_metadata,
    size_t bytes, double pts, struct dvbridge_geometry geometry,
    bool fel_reconstructed, bool force_refresh);
```

The future internal helper receives `force_refresh` and selects refresh=1
before repeat precedence when true. The original prepare/helper preserve
their signatures and behavior through an unchanged-default false wrapper.
Do not perturb PTS, source flags or committed previous payload. Force on first
output, stream reset, policy revision/output-generation change, including
equal-PTS changed revisions. Source scene refresh and existing real-PTS
discontinuity rules also apply. Exact coherent paused repeats reuse the
already qualified image/metadata and stable packet. Staged counters/CRC/ID
publish only on actual successful presentation; failed/superseded candidates
never become the reference for later candidates. Refresh=0/id1 and equal-PTS
new-revision refresh=1/id2 byte fixtures are frozen independently. Current CPU
characterization proves requested packet fields/CRC, not this unimplemented
force_refresh control flow or independent protocol/receiver conformance.

### Deferred GPU boundary, ownership and cost

HDR10 prepare remains synchronous and separate. Enhanced DV requires actual
GLES3.1 compute/SSBO, 128-invocation groups and sufficient scratch limits,
query-verified FP32 arithmetic and Task 6A FP32 render/LUT support, plus
`EXT_buffer_storage` with successful persistently readable coherent mapping.
Storage and mapping both use READ|PERSISTENT|COHERENT; initialize/map once
before submission, never map after a dispatch. No GetBufferSubData fallback.
The [Khronos extension](https://registry.khronos.org/OpenGL/extensions/EXT/EXT_buffer_storage.txt)
requires a real completion sync after server writes even for coherent maps.
Missing functions/flags/allocation/precision return unsupported, not Basic,
previous-frame statistics, blocking readback or silent precision downgrade.
Actual availability on the target and libplacebo/native-GL interoperation
remain runtime gates; `pl_buf_poll(...,0)` is not this completion primitive.

Render the known FP32 image once. Each invocation produces one reduced PQ
sample. Use fixed contiguous pairwise trees of128, with neutral zero padding
for sums/counts and +infinity/-infinity for unused min/max lanes. Ping-pong
partial buffers between ordered dispatches; use SHADER_STORAGE_BARRIER_BIT
before every consuming dispatch. No floating atomics or nondeterministic
subgroup/reordering assumption. Final record is12 u32 words (48 bytes): three
FP32 bit patterns min,sum,max, u32 group_count, three identities as low/high
u32 pairs, validity and reserved0. GPU does not round wire metadata or build
packets. Max groups2073600; maximum sum2073600, so no FP32 range overflow.
Retain the raw scalar CPU binary64 sum/group_count after completion. After
complete finite/domain/count/identity/reserved validation, exact finite
min==max permits that common extremum as the derived mean only if the raw sum
exactly matches the mandated constant FP32 reduction tree and the raw mean
remains within1e-6 of the common value. The scalar-only validator replays
bounded128-lane tiles, at most three levels for2073600 groups; it does not
process pixels or alter GPU reduction/storage. For unequal extrema, require
the raw sum inside the inclusive exact tree enclosure T_N(min)..T_N(max).
Only for metadata derivation, select the nearest measured endpoint when the
raw mean lies outside those extrema; otherwise select the unchanged raw mean.
This Task9 sponsor-approved amendment adds no epsilon or wider error budget.
Snapshots retain raw min/mean/max, FP32 sum and count separately from rounded
selected statistics. Positive five-place and wire rounding remain CPU work;
both five-place and L1 ordering guards remain. Reject corrupt sums and invalid
records before deriving; endpoint consistency is not actual-pixel accuracy.

Fence with `glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE,0)` after final writes,
then `glFlush`. Poll once per scheduled render-thread callback with
`glClientWaitSync(fence,0,0)`; timeout returns pending without reading memory.
Only ALREADY_SIGNALED/CONDITION_SATISFIED permits the48-byte coherent scalar
copy. WAIT_FAILED is failure with quarantined resources, not permission to
reuse. No busy loop, nonzero timeout, Finish, image readback or blocking map.
Fence producer image/scratch uses too; later packer use needs its own last-use
completion before recycling the held image. Source import lifetimes obey
existing libplacebo rules; retain only necessary imports until their actual
last read, never transient metadata field pointers.

There is one slot total, including canceled/retiring work. Supersession/cancel
invalidates publication immediately but moves the slot to retirement, not
free storage. New prepare can return busy until its real last-use fence
signals. Reset clears committed/cache availability and epoch; it cannot
recycle in-flight storage. Destruction hands unfinished resources to the
owning render-context retirement owner, which outlives renderer teardown;
without that owner, destruction is not qualified. Fence failure needs context-
loss handling or safe GPU-owner teardown; no hidden wait/free shortcut.
Caller-owned submitted surfaces retain their independent display-completion
lifetime, unaffected by cancel/reset or engine slot retirement.

At 4K one RGBA32F image is 132710400 bytes (126.56 MiB), normally reusing the
existing intermediate. At most 16200 initial 16-byte partials; two bounded
scratch buffers need <=518400 bytes, plus 48-byte transfer. At 60 fps a full scan
can read 7.96 GB/s before reduction/packing overhead. No extra image ring is
authorized and no throughput/latency measurement is claimed. A pending frame
cannot be presented with prior-picture metadata to hide that latency.

The offline analyzer is binary64, checked against65-digit Decimal controls.
GPU reduction must meet <=1e-6 normalized-PQ raw min/mean/max error against
independent analysis of exact represented binary32 sampled pixels, with the
same active-origin partial2x2 groups and equal group votes. Retain ideal image
I, represented image P and GPU record G separately, including G-A(P),
A(P)-A(I), G-A(I), raw CPU mean and exact mathematical division. Exact frozen
image/L1/packet checks and image budgets remain unchanged. Fixed scalar bits
and count require exact half-up, coding, descriptors, packets, CRC and state.
For fixed GPU inputs, require exact rounded equality when both endpoints of
the unchanged error interval occupy one half-up bin; an exact threshold is
in the upper bin. Code equality is mandatory where all permitted rounded
values yield one code and match the frozen code. Near-boundary/tie raw,
rounded, code and packet differences remain explicit, not biased away.
This sponsor-approved Task8B qualification is an engineering gate, not an
all-domain FP32 proof;100-digit Decimal is not formal interval arithmetic.
No original tolerance, image/source equation or frozen expectation changes.
No GPU execution occurred in Task6B.

### Renderer interface and state contract

```c
enum dvbridge_output_generation { DVBRIDGE_ETSI_LEGACY_LITERAL = 1 };
struct dvbridge_dv_policy_snapshot {
    struct dvbridge_identity identity;
    struct dvbridge_policy policy;
    unsigned source_cm_version; /* 29 or 40, never rewritten as output */
    enum dvbridge_output_generation output_generation;
    struct pl_color_space nominal_target;
    struct pl_color_space container;
    struct dvbridge_geometry geometry;
    double nominal_max_nits; /* ceil(requested double peak), not measured */
    double statistics[3]; /* rounded min,avg,max normalized PQ */
    double raw_statistics[3]; /* min,binary64 sum/count,max before selection */
    float raw_sum; /* original FP32 reduction */
    uint32_t sample_count;
    uint16_t l1[3]; /* min,max,avg wire codes */
    uint16_t source_pq[2]; /* nominal output envelope codes */
    unsigned margins[4]; /* L,R,T,B */
    unsigned max_cll, max_fall; /* zero, unmeasured */
    bool measured, fel_reconstructed, resolved;
    pl_tex final_target; /* historical non-owning token */
    unsigned final_framebuffer; /* captured matching-context authority */
};
struct dvbridge_dv_policy_output {
    struct dvbridge_dv_policy_snapshot value;
    const void *output_metadata; /* borrowed renderer-owned buffer */
    size_t bytes;
    const struct dvbridge_candidate *candidate; /* borrowed */
    pl_tex intermediate; /* borrowed renderer-owned BT2020/PQ image */
    uint64_t resolve_serial; /* capture for actual caller submission */
};
enum dvbridge_dv_policy_status {
    DVBRIDGE_DV_FAILED, DVBRIDGE_DV_UNSUPPORTED, DVBRIDGE_DV_BUSY,
    DVBRIDGE_DV_PENDING, DVBRIDGE_DV_READY, DVBRIDGE_DV_IDLE
};
enum dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare(
    struct dvbridge_renderer *renderer, const struct dvbridge_policy *policy,
    const struct dvbridge_identity *identity, const struct pl_frame *source,
    const void *metadata, size_t bytes, double pts, double el_pts,
    struct dvbridge_geometry geometry);
enum dvbridge_dv_policy_status dvbridge_render_dv_policy_poll(
    struct dvbridge_renderer *renderer);
const struct dvbridge_dv_policy_output *dvbridge_render_dv_policy_output(
    const struct dvbridge_renderer *renderer);
bool dvbridge_render_dv_policy_resolve(struct dvbridge_renderer *renderer,
    pl_tex caller_target, unsigned final_framebuffer, bool flip_y);
bool dvbridge_render_dv_policy_commit(struct dvbridge_renderer *renderer,
    const struct dvbridge_identity *presented_identity, pl_tex presented_target,
    uint64_t submitted_resolve_serial);
void dvbridge_render_dv_policy_cancel(struct dvbridge_renderer *renderer);
bool dvbridge_render_dv_policy_committed(const struct dvbridge_renderer *renderer,
    struct dvbridge_dv_policy_snapshot *caller_snapshot);
struct dvbridge_retirement_owner *dvbridge_retirement_owner_create(pl_gpu gpu);
struct dvbridge_renderer *dvbridge_renderer_create_with_owner(
    struct dvbridge_retirement_owner *owner);
enum dvbridge_dv_policy_status dvbridge_retirement_owner_poll(
    struct dvbridge_retirement_owner *owner);
bool dvbridge_retirement_owner_destroy(struct dvbridge_retirement_owner **owner);
```

The output/snapshot contain value copies of identity, policy, source generation,
output generation, nominal envelope/gamut, BT2020/PQ descriptor, rounded
statistics/L1, L5 and flags for full FEL and resolved state. Output additionally
exposes borrowed owned output-metadata/candidate and exact borrowed intermediate;
the committed snapshot is value-only with a historical non-owning final-target
token. Getters return NULL/false before readiness/commit respectively. No GPU
pointer is published as completed before poll. `dvbridge_render_texture` can
expose the same intermediate only at READY; it does not extend its lifetime.

`DVBRIDGE_DV_POLICY_API=2` requires explicit final-framebuffer authority.
Store that FBO with the borrowed target wrapper in its matching native context;
never infer zero from a failed unwrap or a late unrelated binding. Opaque
target/FBO pairing is an explicit caller assertion. Pinned LP opaque wraps
allocate a distinct queried format; texture formats use the public GPU format
registry, permitting additional checked unwrap/attachment matching without
the unsupported opaque texture unwrap. Real framebuffer completeness, linear
encoding and exactly RGB8 with absent alpha or RGBA8 with alpha8 are checked
against the queried wrapper representation, with bindings restored on rejection.
Other component counts/depths, alpha mismatches and multisampling remain rejected.
Framebuffer 0 is deliberate valid authority, not a fallback. Resolve stores
the exact target/FBO and monotonically increasing serial; commit still requires
the actual successful caller submission's identity/target/captured serial.
Caller retains output through GPU use and display completion; wrappers transfer
no external framebuffer/texture ownership. No replacement target or blit is added.

Prepare snapshots immutable source/policy/identity, validates finite real PTS,
exact source/FEL pairing and identity.revision==policy.revision. The revision
names all policy/profile/generation/source changes; changed values with a reused
revision are a caller error, not a paused-cache hit. Poll can create CPU metadata
and a candidate only for that slot/epoch. All access is render-thread confined.
Poll also services one retirement check after cancel/reset/commit: BUSY while
the last-use fence is unsignaled, IDLE when safely retired with no pending
picture. READY polling is idempotent and never reserializes. The state tables'
"retire" event denotes this same poll callback, not an additional runtime API.
Resolve composes existing GUI into the same qualified image and invokes the
existing separate DV packer into the caller's exact3840x2160 RGB8/alpha0 or
RGBA8/alpha8 target,
with no second mapping/enhancement. Metadata analyzes video, not GUI. Borrowed
pending views expire on next prepare/cancel/reset/commit. The slot owns image,
source/policy snapshot, scalar/scratch/fences and output metadata until safely
consumed/retired, never transient caller metadata fields.

The Task9 bounded compatibility amendment admits real opaque RGB8 targets
without inventing stored alpha. Transport and metadata use only RGB; the unchanged
packer writes constant unused alpha on RGBA targets. Actual RGB8 renderbuffer and
alpha-zero pbuffer controls compare all transport RGB bytes, all 128 uint32_t
packet words (512 storage bytes representing 128 logical byte values), metadata
and source identity against real RGBA8 for identical prepared inputs. Exact target,
captured serial and commit authority remain mandatory. This does not change the
public API, native format selection, Standard/Basic, numerical operations or budgets,
and does not qualify native teardown or physical display behavior.

Commit requires the latest READY+resolved candidate's exact identity and exact
final target, after successful actual submission/presentation. It succeeds
once and advances existing CPU context plus committed value snapshot together.
Every successful resolve invalidates any prior submission, including a resolve
to the same target. Only a subsequent submission of that latest exact target
can commit; rejected stale-target commits preserve the prior committed state.
The caller captures `resolve_serial` when submitting, carries it in that actual
successful submission's completion record, and supplies that exact serial to
commit. Identity and target alone cannot distinguish same-target resubmission.
Serials increase over the renderer lifetime, including reset. Zero, old serials
and overflow cannot publish. Existing Standard/HDR10 commit APIs are unchanged.
Wrong identity/target, unresolved candidate, failed presentation or old epoch
cannot advance. Presentation failure calls cancel; failed prepare/resolve/poll
invalidate paused availability but preserve prior committed descriptor. A
coherent paused identity reuses the retained caller final surface or still-
valid cached image/metadata; never enhance a transformed image again. No
available retained surface means fresh treatment of original immutable source.
Seek/new stream resets frame caches and committed availability, not preferences
or caller display-in-flight surfaces.

The external owner holds one attached renderer or detached retirement lease,
including its engine-owned image, scratch, scalar mapping, programs and fences.
It borrows `pl_gpu` and the GL context: the caller must retain a usable current
context and GPU until owner destruction returns true. `pl_opengl` has no
refcount. Destroy returns false while attached or retiring, never waits, and
nulls the owner pointer on success. Detached owner poll performs one zero-timeout
completion check. WAIT_FAILED, failed fence creation or unusable context imply
safe quarantine, not reusable recovery. Decoder/import handles and caller
display-in-flight surfaces have separate caller-owned last-use lifetimes.

Task8B implements this software path under the sponsor-approved represented-
image and exact constant-population amendments of2026-10-02. Historical failed
receipts remain retained. The committed candidate requires independent review;
native software GL evidence does not establish receiver, physical-GPU or Kodi
submission qualification.

55 paired fixtures use complete synthetic rasters: 36 accepted non-neutral FEL
full/scaled outputs, 12 newly compiled neutral-FEL outputs, 7 analysis boundaries.
Small rasters test analyzer arithmetic and full synthetic composition, not a
3840x2160 hardware pass; separate complete uniform-raster geometry descriptions
and exact L5 packets test every half-pixel side/downscale. All pair images come
from independent compiled source controls or explicit synthetic pixels;65-digit
Decimal statistics and polynomial-division CRC expectations are separate from
the evaluator/current CPU serializer. Three independent state tables cover
defer/visibility, commit twice, repeats, equal-PTS revision, failures, wrong
result, supersession, busy retirement, reset/new stream and unsupported paths.
Registered tests characterize the existing CPU serializer against the frozen
bytes when its explicit control is configured; without it that check reports
a skip. Exact fields/packet checks are software carriage evidence only.

Remaining gates: independent6B review/sponsor addendum approval; runtime C/GL
implementation and numeric/lifetime/latency qualification; actual receiver
constants/degeneracy/temporal and nominal-descriptor acceptance. Full transformed
CM4 creative re-authoring is unsupported. Historical fused/Lanczos failures,
source-tree damage and Python leak-disabled characterization remain open.

## Authority

Dependency archive, patch and modified-source identities are locked in
`config/dependencies.json`. libplacebo is pinned to
`e2972fdd09adacd383656738d7d280f0cd84a761`, not current upstream. FFmpeg uses the
locked 9.0 archive with matched patched producer/consumer headers. Historical
extraction receipts are unchanged.

Inspected configured libplacebo files and SHA256:

| Path | SHA256 |
| --- | --- |
| `src/include/libplacebo/utils/libav_internal.h` | `542055662c561cbccbb479a89be0ed1b6e295bbc7b2298a83d8424d053d14189` |
| `src/colorspace.c` | `0099300821d9960dd291f2b6ac22eb5779e95326ae327c488030268e8c02f5e3` |
| `src/tone_mapping.c` | `facf351719c56a9d15ce279d64eb0cb985ece85f101d04d7874547e27b61c8f6` |
| `src/gamut_mapping.c` | `cfc6f906871f506517d8ecc4dcc7201a464da579443a6b81a47aa0fa9f72d32d` |
| `src/shaders/colorspace.c` | `a418ca3c3439febada2e1109f378474ecc2230be06e9f610b3d7a3d680fd5588` |
| `src/renderer.c` | `ffd96f4f04cb2d565d661d6bb0a76fffb90be988a49e90771877219053edf808` |
| `src/include/libplacebo/shaders/custom.h` | `eb7c317f6c93ce76a67f5e622d5c784e702545752a88535a4eb577fdcc74e50e` |
| `src/include/libplacebo/colorspace.h` | `045ae8a75caa8d1dc50dcfdf1b190817af3a07c0d381df20d86178095dab9a0d` |
| `src/include/libplacebo/tone_mapping.h` | `dcf32f6eca4aa4e323c1396a5f1359922c5117e3f3eab845b4b5d674598f471e` |
| `src/include/libplacebo/gamut_mapping.h` | `a75332f7d17b2cb55e7b16a9bcb6a88b639ec957809a7913876cab1acfe0bf69` |
| `src/include/libplacebo/common.h` | `d61d6425038783aa93582d80d8e828ecb63fcfb6c6f9d5d1577e95d3996f4f10` |
| `src/shaders/lut.c` | `b8cd0651316df5accec9c2bc16f260378baeed2461915a0ad7f6c3a4dd47c3d3` |
| `src/tests/tone_mapping.c` | `f34c8cc4923d36f78595dd2757800a1185792d56478bc26da1a227658bb38cc5` |

The inspected files carry LGPL-2.1-or-later notices. Tests use public APIs and
independent arithmetic, not a proprietary implementation or SDK. Historical
standards and authoring-guide provenance remains in the integration readiness
audit; scalar coding examples are not a Dolby image oracle.

## Independent foundations

`evaluate(case) -> dict` computes from inputs only. `check(case, actual)` compares
to separately frozen expected values in `vectors.json`. Unknown operations,
missing domains/expected values, unexplained comparison limits, duplicate IDs
and scalar-only coverage of an essential image operation are rejected.

`CB1_PQ_RESCALE` is an ideal binary64 foundation, not an actual public-API
representation claim. Its six existing vector IDs, values and 1e-12 PQ / 1e-9
nit limits are unchanged. It uses absolute 10000-nit ST2084 scaling and the
pinned zero convention. `PL_HDR_NORM` is nits/203, not nits/10000 or normalized
PQ. These ideal limits are not public-library or runtime GPU image limits.

`pl_map_avdovi_metadata` divides L1 max/average codes by 4095.0f and stores
binary32 `max_pq_y`/`avg_pq_y`. `CB1_L1_LIBRARY_REPRESENTATION` now checks this
source-defined representation with exact fixed values and uint32 bits. All
12-bit codes and the divisor are exactly representable; correctly rounded
binary32 division supplies the field value. The old `l1-dark`/`l1-high-key`
vector IDs, values and 1e-15 limits are preserved under
`CB1_L1_IDEAL_DIVISION`, domain `ideal binary64 PQ hints`. They do not qualify
float storage. For example, 2048/4095 rounds to 0.5001221299171448, bits
0x3f000801; 512/4095 to 0.1250305324792862, bits 0x3e000801; 3079/4095 to
0.7518925666809082, bits 0x3f407c08. Zero and 4095 are exact endpoints.

`vectors.json:public_pq_cases` is separate external-library characterization,
not part of the ideal evaluator. An independent direct ctypes probe was
frozen before evaluator support. `evaluate_public_pq` compares API float
values and uint32 bits exactly against that receipt. The rule is zero error
for this recorded Linux x86_64, glibc 2.39, 64-bit ABI and hash-pinned binary,
not a portable libm contract, independent proof of libplacebo, mathematical
PQ error bound or GPU acceptance rule. The public API uses float/powf and
the nits/203 intermediate; it is not binary64 ST2084 rounded once. At 100 nits
its frozen output is 0.50807785987854 (0x3f021164), and decoding 0.5 yields
92.24369049072266 nits (0x42b87cc5). Do not use ideal limits for these outputs.
The explicit-library unit run checks all six API receipts. Without its path,
this external check is explicitly skipped, never presented as ideal evidence.

FFmpeg labels L1 per-frame brightness metadata; it does not establish that
authored maxRGB statistics are measured CIE-Y. ETSI's separately named
4096-based coding is not silently substituted into the pinned reader.

Nominal TV target: configured peak unchanged, named BT709/P3-D65/BT2020 gamut,
PQ, and `PL_COLOR_HDR_BLACK` (1e-6 nits) as a library infinite-contrast sentinel
for either panel type. Neither panel type creates a measured contrast or
full-screen brightness model. The final HDR10 container is BT2020/PQ even for
a smaller nominal destination gamut. Descriptor max luminance rounds upward;
minimum luminance and unmeasured output MaxCLL/MaxFALL signal zero. Source
mastering and source statistics do not become measured transformed output.

## Proposed isolated Natural/Intense policy

This is CB1's own policy, not Dolby creative processing. Apply only to already
mapped linear RGB in the nominal destination primaries, before conversion to
the BT2020 container, PQ encoding, borders or GUI. All RGB components must be
finite. A coordinator-approved Task 6B correction projects mapper excursions
into `[0, peak]` at the entrance, before the unchanged selective equations.
The same nominal gamut and configured peak apply to both presets and both
Enhanced formats. Full DV eligibility remains separately qualified by the
experimental metadata and receiver gates above.

Shared Enhanced-only nominal-cube projection: if all components are in
`[0,peak]`, return the original RGB exactly. Otherwise let
`a=clip((min(RGB)+max(RGB))/2,0,peak)`, `v=RGB-a`, and
`t=min(1, (peak-a)/v[c] for v[c]>0, -a/v[c] for v[c]<0)`.
Ignore zero directions. Return `a+t*v`. Limiting components equal their
mathematically exact zero/peak endpoints, rather than retaining cancellation
roundoff. Reject nonfinite input/arithmetic. This is one common neutral-anchor
contraction, not independent channel clipping, new gamut mapping or a source
statistic repair. It preserves the direction of the midpoint-opponent vector
in this RGB substage and contracts its magnitude; no perceptual hue equivalence
is claimed. Uniform below/above-cube gray reaches exact black/white. Entirely
in-cube images, Reference Expert, Basic/Standard and all old fixed expectations
remain unchanged. The original isolated policy rejected all outside-cube
inputs; accepting finite mapper excursions through this exact projection is
an explicit own-policy change, not a widened tolerance.

At peak 100, independent rational upper/lower/mixed controls are
`[110,50,10]->[100,52,20]`, `[-10,50,90]->[0,48,80]`, and
`[-10,50,110]->[0,50,100]`. Small-detail controls preserve a green-channel
increase from 50.0000000099999 to 50.0099996400072 while red is exactly 100.
Above-ceiling maximum-channel detail can collapse at the cube boundary;
there is no strict maxRGB ordering claim outside the nominal cube. The
unchanged in-cube selective curve retains its existing strict-order controls.

The need is independently demonstrated, not inferred from a test typo:
neutral-FEL source pixel 10 reconstructs BT2020
`[1293.9361759999942,235.5160925000137,147.76001050000215]` nits.
For a 1500-nit BT709 target, LUT output before enhancement is
`[1500.1749828790958,142.08216296627683,125.74509622393816]`.
Independent C and Python agree. Unquantized float-LUT interpolation instead
gives red 1500.3299836241306, so UNORM packing alone is not the cause.
The pinned shader converts IPT to linear RGB without a final cube clamp;
its approximation can cross that boundary. The accepted non-neutral FEL
counterpart red is 1494.3938034507196 and needs no projection. Frozen new
neutral images come from a separate C control with the exact new projection;
the four original failing controls/run remain retained. No library, runtime,
source reconstruction, Reference Expert arithmetic or old tolerance is changed.

Let `S(a,b,x)` be clamped cubic smoothstep, `v=RGB/peak`, `m=max(v)`, and
`d=1-0.5*S(0.1,0.5,a)`. `a` is the decoded source L1 average hint divided by
the decoded maximum hint. It is a content-dependent proxy, not CIE-Y, a mean
linear-nit statistic, or output FALL. Source L1 remains unchanged; the
source-policy/image contract is defined in the continuation below.

`shadow=S(0.01,0.02,m)`. Natural uses `onset=S(0.25,0.75,m)` and `k=0.20*d`;
Intense uses `onset=S(0.02,0.25,m)` and `k=0.35*d`.

`m'=m+k*shadow*onset*m*(1-m)` and `v'=v*m'/m`. Exact zero and all pixels with
`m<=0.01` bypass the policy unchanged. Neutral pixels with no brightness change
also bypass round-trip arithmetic. The maximum-channel curve is strictly
monotone: its derivative is at least `1-k>=0.65`, because both masks are
nondecreasing. It cannot force an interior value to 1 or introduce a compulsory
scene peak. Common-channel gain preserves linear chromaticity at this substage.

Color expansion uses midpoint-opponent coordinates, not a claimed perceptual
or constant-CIE-Y space. With `g=(min(v')+max(v'))/2`,
`c=(max(v')-min(v'))/2`, `h=min(g,1-g)`, let `t=min(1,c/h)` when `c,h>0`.
Natural chroma strength is `b=0.04*shadow*d`; Intense is `0.08*shadow*d`.
`f=min(1+b*4*t*(1-t), h/c)` and `v''=g+f*(v'-g)` componentwise. Zero chroma
and cube boundaries are protected; the headroom bound prevents channel
clipping. This is selective, not a uniform saturation multiplier. The opponent
direction is preserved, but no perceptual hue-error bound is claimed until
the full image gate supplies one. These operations do not need a spatial filter
or another GPU pass. Custom masks address the gap that the accepted Basic
spline/perceptual operators do not implement selective enhancement.

Independent rational examples for a 1000-nit source and 1500-nit target:

| Pixel / scene | Natural | Intense |
| --- | --- | --- |
| neutral 1000, dark `a=0.02` | `1500*172/243 = 1061.7283950617284` | `1500*67/90 = 1116.6666666666667` |
| neutral 1000, high-key `a=0.5` | `1500*167/243 = 1030.8641975308642` | `1500*127/180 = 1058.3333333333333` |
| neutral 750, dark | `787.5` | `881.25` |
| neutral 150, dark | `150` | `150 + 1500*(7/20)*(3392/12167)*(9/100)` |
| zero / nominal cube primary at peak | unchanged | unchanged |

For `[1000,500,250]`, dark-scene midpoint ratio gives `t=3/5`; color factors
are exactly `649/625` and `673/625`. Fixed vectors use these rational
derivations, not evaluator output. `1e-9` nits covers binary64 arithmetic
roundoff only. The continuation below now freezes a separate future GPU/PQ
engineering acceptance bound; it is not evidence that a GPU meets that bound.
No preset values are taken from an ignored draft.

## Historical checkpoint and public facilities

The public pinned `pl_tone_map_generate/sample`,
`pl_gamut_map_generate/sample`, `pl_ipt_rgb2lms/lms2rgb` and exported IPT matrices
provide a feasible external library-characterization reference. This is
independent of the CB renderer, not independent validation of libplacebo itself.
Upstream `src/tests/tone_mapping.c` supplies black/white, neutral-curve and
primary checks, but not a complete CB1 reconstructed-image fixture.

Runtime shader behavior includes IPT tone/chroma coupling and 48x32x256 ICh
gamut LUT lookup packed into UNORM16. Direct `pl_gamut_map_sample` alone is not
equivalent. A bounded offline reference must characterize LUT generation,
packing/interpolation, working gamut to BT2020 container conversion, and the
new selective policy before final images and acceptance rules are frozen.

The bounded characterization now implements public CPU LUT generation and
endpoint-aligned eight-corner interpolation for all three nominal gamuts.
The reused Linux binary SHA256 is
`111c6084a8e509f27e2c586e33568c82bf28c778c44b2740230e9bb1571f65af` and
`pl_version()` returns `v7.372.0`. This is an installed-prefix receipt, not a
fresh upstream build or binary portability promise.
An independent compiled public-header receipt confirms the 64-bit ABI sizes
HDR=148, tone params=248, gamut params=120 and offsets tone HDR=92, tone LUT
size=64 and gamut constants=80. The Python adapter remains test-only.

`fill_gamut_lut` adds 32767 to packed opponent channels, while the shader
subtracts 32768 after lookup. The reference therefore characterizes an exact
`-1/65535` neutral bias before floating subtraction error. This is source/LUT
characterization, not a newly qualified CB runtime defect. No production patch
or tolerance change follows from it. Full image readiness must establish
black/neutral behavior, including any separately justified exact-zero guard.

The installed library is sanitizer-instrumented and needs ASan preloading in
the Python host. Leak-enabled characterization exits with interpreter
allocation leaks. A separate leak-disabled offline characterization passes;
it is not a leak-free or complete sanitizer claim. Compiled engine sanitizer
and leak settings remain unchanged.

Essential rows must stay blocked whenever their image contracts are incomplete. The
validator independently requires image coverage for all seven required image
stages, including source-scene policy, and both isolated policy stages whenever
ready. Editing their row declarations to scalar cannot lower that minimum.
An image declaration with only scalar evidence is also rejected. The twelve
historical creative gaps may remain honestly not applied; they are not
a requirement to reproduce the proprietary mapper and cannot excuse omission
of CB1's required image stages.

## Complete offline image continuation

`image_reference.py` is a focused test-only addition. Source-equation
composition informed by libplacebo is LGPL-2.1-or-later, with the existing
`LICENSES/LGPL-2.1.txt`; scalar/validator tests keep their existing MIT license.
It independently expresses equations and calls public CPU APIs. It does not
copy a proprietary mapper, call CB rendering, or produce its own expectations.

The separate retained C controls supply 88 fixed image vectors, including
36 complete unscaled and 18 complete scaled RGB/PQ outputs. Its source and
full commands are retained with the Task 6A image report, not shipped as a
second source owner. The control uses binary64 composition, public binary32
matrices/LUT entries and explicit binary32 UNORM16 packing. A separate C
scaler control fixes Lanczos and Hermite outputs and ABI sizes
FilterConfig=80, FilterParams=104, Filter=136 on the recorded 64-bit host.
Three hand-enumerated state tables and six binary32 capability vectors are
independent of both image evaluators. Original ideal and public PQ receipts
and tolerances remain unchanged.

### Reconstruction, source resolution and geometry

Normalized decoded component samples, RPU and EL have identical stream,
picture and revision identities. Missing/mismatched applicable FEL fails the
requested treatment, never BL-only success. Input metadata remains immutable.
Public `shaders/colorspace.c:51-306` defines clamped piecewise polynomial/MMR
reshaping. The reference accepts 2..9 ordered pivots, polynomial orders <=2,
and MMR orders 1..3 with monomials x,y,z,xy,xz,yz,xyz, raised per order.
Non-neutral FEL fixtures use signed offsets +1, -1, +64 and -32 EL codes.
`utils/libav_internal.h:993-1020` and `shaders/colorspace.c:106-151` define
LINEAR_DZ. Independent code-space residual is
`sign(rr)*((abs(rr)-0.5)*S+T)/2^denom`, exactly zero for rr=0.
The shader's two-ULP neutral cancellation guard remains unchanged. EL sampling
is paired full precision; integer fixture samples avoid inventing a GPU
roundoff oracle. YCC/offset, PQ EOTF, source linear matrix and the pinned HPE
inverse in `shaders/colorspace.c:450-486` complete BT2020 linear reconstruction.
The fixture's equal HPE values are neutral residual controls, not an assertion
that the approximate published HPE inverse has exactly unit row sums.
Three additional independently compiled fixtures cover nonidentity piecewise
polynomial reshaping at/below/above its .5 pivot, three-order MMR with all seven
monomials, and nonidentity YCC/offset/linear matrices. They are reconstruction
RGB/signal controls, not plausible measured display images or exhaustive RPU
validation. Negative/out-of-cube matrix outputs are retained at this stage.

Source minimum/maximum PQ codes are integer 0<=min<max<=4095, consumed through
binary32 `/4095.0f` then public PQ-to-nits conversion. One usable matched L1
is required. One valid L6, if present, supplies already decoded minimum and
maximum nits; otherwise RPU source PQ supplies mastering. Duplicate/invalid
L1/L6 or essential reconstruction data rejects treatment. Absent optional
creative blocks and present-zero blocks are equally not applied. L1 min is
not silently substituted for mastering black. Source L1 maximum/average hints
remain binary32 PQ; decode both through public API, divide in binary64 for
the own-policy scene ratio. This ratio is not CIE-Y or measured FALL.
CM2.9/CM4 is carried truthfully without stacking creative operations.

Reconstruction precedes main scaling and color mapping. The pinned renderer
defaults (`renderer.c:207-215,606-652,2146-2204`) select one filter/domain for
the complete resize: any shrinking axis selects linear-light Hermite for both
axes; otherwise Lanczos3 in PQ, no HDR sigmoid. Both passes use that selection,
vertical before horizontal (`renderer.c:755-783`), without intermediate
transfer conversion or clamp. The reference calls public
`pl_filter_generate` with 256 phases, row alignment 4, blur=max(1,1/ratio),
then endpoint-aligned phase interpolation, clamp-to-edge source taps and
explicit sum-of-weights normalization. `sampling.c:962-1140` defines the
separable operation. Scaling shader PQ transfer uses `colorspace.c:679-684,
728-737,820-823,867-875`: encode once before PQ filtering, decode once after
both passes, and clamp negatives only. Do not clamp PQ super-whites to one.
Shader PQ at zero is `(3424/4096)^(2523/32)`, unlike the ideal/public-rescale
exact-zero convention preserved above. EOTF and constant-black convolution
still return exact black in the fixed controls, consistent with final zero.
Two-axis overshoot and mixed-axis independent controls freeze this difference;
the former retains vertical signals below zero/above one and filtered nits up
to 37419 before mapping. Existing horizontal-only controls remain unchanged.
Main two-dimensional scaling is separable. Identity
geometry bypasses filtering. Borders are applied at output pixel centers
after video mapping and before GUI. Final vertical flip follows GUI and
precedes resolve. Existing exact Lanczos and fused controls remain unchanged
and unresolved; this numerical reference does not waive them.

### Complete display/gamut/preset composition

Select `pl_tone_map_spline`, the fixed constants above, 256 tone entries and
perceptual gamut mapping with 48x32x256 ICh entries. Source primaries and input
gamut are BT2020; destination primaries and output gamut are the named nominal
preset. A live libplacebo state and linear UNORM16 LUT format are mandatory;
absence fails treatment, never the source's silent linear/saturation fallback.
The nominal black sentinel is converted to exact signal zero for tone/gamut
minimum, matching `colorspace.h:26-29` and shader placement.

Tone input maximum is max(L1 max PQ, target PQ), average is L1 average PQ,
input minimum is source mastering minimum unless <= sentinel, then zero;
output minimum is zero, output maximum target PQ. Use the actual public
no-op decision. Below-target source is not inverse-mapped or forced to peak.
On the full path, BT2020 RGB nits is converted with public IPT RGB->LMS,
ST2084 per LMS component and exported LMS->IPT matrix. Tone changes intensity
through the generated linear 1D LUT. Opponents are multiplied by
`min(I_orig/I_new, h(I_new)/h(I_orig))`, h(I)=I^3-6I^2+9I.
Exact black bypasses the full color round trip and remains exact zero.

Task 7 source-anchored mapper-domain clarification: the forward mapper uses
the existing negative-only guard on finite LMS nits, not an upper clamp to
10000. Its inverse likewise guards negatives only, not PQ super-whites to one.
These are the pinned shader equations and retained independent C authority
(`task-6A-image-control.c:135`, fix1 output control `:143`). The test-only
`mapper_pq_encode`/`mapper_pq_decode` implement that finite extended domain;
standalone bounded scalar PQ contracts, exact-zero conventions, no-op behavior,
every historical vector and comparison limit remain unchanged. The inverse
domain ends before `(2413/2392)^(2523/32)` (approximately 1.9920600818564766),
where the denominator reaches its pole; nonfinite/pole-domain reference input
fails explicitly rather than inventing a clamped value. No runtime guard changes.
Independent C composition of the three additional complete two-axis outputs
records nine forward upper-cap activations (max LMS 28529.805394241674 nits)
for the overshoot case and zero reverse upper-cap activations. Reverse-domain
boundary coverage therefore is not claimed as the cause of its previous error.
These new expectations are separate from the unchanged original 19 GPU images
and signed source/scaler fixtures. Their final PQ/code/black/detail/hue limits
are the original limits, not intermediate linear-nit acceptance criteria.

Gamut coordinates are I/targetPQ, 2*length(P,T),
atan2(T,P)/(2*pi)+0.5. Generate all entries with the public library, reproduce
binary32 packing with opponent bias 32767, interpolate eight packed corners,
then subtract 32768/65535. Convert back with exported IPT->LMS, ST2084 EOTF
and the nominal destination LMS->RGB matrix. Actual no-op BT2020 gamut skips
the LUT, rather than introducing its packing bias. The bias is characterized,
not hidden, compensated arbitrarily or reported as a runtime defect.

The new Expert preparation requires actual FLOAT4 depth32/host32 LINEAR
orthogonal scaler-LUT storage via a CB-owned, default-off format option.
It preserves existing binary32 weight generation, positive-kernel pairing,
256 phases, filters, addressing and pass count. The real format capability
lookup returns NULL when unavailable; the engine rejects sampling errors even
if the pinned renderer attempts a fallback. Passing the explicit format into
the existing LUT cache identity protects false/true transitions. Native/Basic
and Standard keep their defaults, including automatic half storage. This is
not a polar-sampler change or physical-GPU capability claim.

Policy-only stable PQ emission is default off. Its existing shared inverse
helper uses q<=0 -> zero without evaluating log; otherwise z=log(q)/78.84375,
y=z/16, d=-y*(1+y*(1/2+y*(1/6+y*(1/24+y/120)))), four d=d*(2-d)
doublings, max(.1640625-d,0)/(.1640625+18.6875*d), and the original final
power 1/.1593017578125. This fixed general expm1 seed has analytic 1/n!
coefficients: a bounded primitive approximation, not an exact identity or
fitted ST2084 curve. The unchanged forward helper uses the equivalent ratio
and integer/fractional power split. Source linearization, DV source transfer
and reverse LMS mapping share the opted-in helper; native/Basic retain their
original emitted arithmetic and default-off reset/dispatch behavior. Negative
super-white deficits and the original finite inverse pole are not clamped or
guarded. No floor, epsilon, custom log, extra pass or altered image budget is
introduced. Host receipts do not establish uniform hardware precision near
that pole, proprietary creative equivalence or physical display qualification.

Natural/Intense is applied exactly once to this mapped nominal RGB cube.
It does not process reconstructed raw PQ or GUI. Both use requested peak and
shared limits. The 1000-nit L6 source/1500-nit target fixtures contain both
decoded-L1 scene ratios; a separate underreported-source stress regime maps
L1 max code 3696 to a 600-nit target and exercises nontrivial spline/chroma
coupling. All three gamuts, both generations and both presets have complete
outputs. Source mastering is not a hard pixel clip or compulsory output gain.

Convert nominal RGB to BT2020 container RGB using public standard-primary
RGB->XYZ and XYZ->BT2020 matrices, then encode PQ once. Public matrices are
binary32 API receipts; double composition does not relabel them exact ideal
primaries. Independent complete PQ output freezes this conversion.
GUI pixels supplied to the reference are already BT2020/PQ and blended only
after policy/borders. No tone or gamut mapper runs at final resolve.
For b in [10,16], full code=floor(PQ*(2^b-1)+0.5), limited
code=floor(16*2^(b-8)+219*2^(b-8)*PQ+0.5). Dither is disabled in this new
policy contract; existing Basic's dither behavior is untouched.

### Positive target range and capability outcomes

The valid saved profile and requested double peak remain `(0,10000]`.
Binary32 round-to-nearest has half-ULP error <=2^(frexp_exponent-25), or
2^-150 in the subnormal domain. Ordinary rounding is represented, not rejected.
Underflow/nonfinite float, requested peak <=1e-6, or represented peak <= the
binary32 sentinel fails only the requested treatment. No clamp, inferred
10000-nit target, invalid-profile label or settings change is allowed.
This is proposed handling under the existing failure rules, pending sponsor
approval, not implemented user behavior.

Above the sentinel, require public target PQ strictly greater than public
sentinel PQ before nominal inference. The pinned float/powf API maps the next
binary32 nits above the sentinel to the same PQ, and 1.000001e-6 nits to a
slightly lower PQ. Both fail explicitly as a collapsed PQ range; this names
the representation limitation rather than inventing an extreme-dim mapper.
Independent frozen front-door capability cases plus assertion-failing public
range fixtures cover below/equal/above/underflow and ordinary rounded peaks.
Digital output precision remains chosen by the existing caller. Quantization
may erase sub-code detail; it is not measured TV luminance or a new calibration
field. No successful full-image fixture relies on implicit target inference.

### Comparison domains and acceptance

Offline C/Python agreement is 1e-6 nits per linear image component: relative
1e-10 at the 10000-nit domain endpoint, allowing double libm/matrix summation
roundoff only, not float GPU execution. Coded reconstruction signal uses
1e-12, source PQ fields/mastering are exact public or integer values, the
binary64 scene ratio uses 1e-12. Complete PQ uses 1e-10 and integer resolve
codes exact. Original horizontal source-derived scaler controls use 1e-8 nits
below 140 nits. New complete-resize controls use 1e-6 nits below 40000 filtered
nits, a 2.5e-11 endpoint relative double-composition allowance, not GPU error.
Packing, LUT discretization and bias are part of the expectation, not error
allowances. `component_limits` avoids using a nits limit on PQ/identity/codes.

Future GPU full-image acceptance is separately fixed before implementation:
component absolute PQ error <=1/65535, less than 1/16 of a 12-bit code;
zero video/borders remain exactly zero; output code deviation <=1 from
rounding-boundary movement, with exact black code. Ramps must remain strictly
ordered, including near-black and highlight steps. At PQ opponent magnitude
>=0.01, midpoint-opponent direction differs by <=0.1 degree from the frozen
reference; below this, extra channel spread <=2/65535. The standalone checker
first requires consistent nonempty RGB/code raster lengths, exactly three
components, finite non-boolean RGB and integer non-boolean codes. These are explicit
engineering acceptance budgets, not a universal GPU transcendental-error
proof, perceptual hue metric, physical display tolerance or measured pass.
`check_image_integrity` executes those rules and rejects altered black,
near-black and non-neutral pixels. Numerical conformance is not subjective
improvement or Dolby creative equivalence. Native comparison stays separate.

## Run

```sh
python3 -m unittest discover -s tests/reference -p 'test_*.py' -v
python3 tests/reference/reference.py
python3 tests/reference/reference.py --runtime
# Explicit pinned-library path and sanitizer preload are supplied by the runner.
python3 tests/reference/reference.py --characterize
python3 tests/reference/reference.py --characterize-lut
```

With the explicit library environment, the first three commands check complete
offline contracts. Without it, the default command explicitly reports skipped
images, and `--runtime` fails instead of claiming full numerical execution.
This flag means complete essential numerical readiness, never runtime approval.
CTest registers these checks; green tests are not full renderer qualification. Existing fused
capability and exact Lanczos failures remain open with unchanged tolerances.
