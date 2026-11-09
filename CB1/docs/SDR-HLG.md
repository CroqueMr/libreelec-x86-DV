# SDR and plain HLG engine contracts

The existing renderer, import, spatial fit and policy presentation owner remain authoritative. Numeric mode and circuit identities are appended: SDR mode 7; DV SDR circuit 14; HDR10 SDR circuit 15; HLG DV Reference circuit 16.

## SDR values and presentation

`dvbridge_policy.sdr` is independent of `tv` and the Expert HDR calibration. `DVBRIDGE_SDR_REFERENCE` resolves to 100 nits, gamma 2.4 and zero black. `DVBRIDGE_SDR_BRIGHT` resolves to 200 nits, gamma 2.2 and zero black. `DVBRIDGE_SDR_CUSTOM` accepts finite peak 20–500 nits, gamma 1.8–2.8 and black 0–5 nits strictly below peak. These are rendering references, not brightness measurements. `dvbridge_sdr_target(profile, &peak, &gamma, &black)` resolves and validates values without changing the profile.

```c
bool dvbridge_render_sdr_policy_rgb(struct dvbridge_renderer *renderer,
    const struct dvbridge_policy *policy, const struct dvbridge_identity *identity,
    const struct pl_frame *source, const void *metadata, size_t bytes,
    double pts, double el_pts, struct dvbridge_geometry geometry);
bool dvbridge_render_sdr_policy_resolve(struct dvbridge_renderer *renderer,
    pl_tex target, bool flip_y, bool limited, unsigned bits);
```

Prepare receives the original picture. Null metadata and zero bytes select original PQ BT.2020 HDR10/HDR10+. DV metadata selects the existing complete BL/RPU/EL reconstruction; required FEL and exact EL PTS remain mandatory. This route does not create outgoing DV transport packets. No HDR/DV sink capability is required by these functions.

Use existing `dvbridge_render_policy_output`, `dvbridge_render_policy_commit`, `dvbridge_render_policy_cancel` and `dvbridge_render_policy_committed`. Output identity and successful resolve/presentation assertions are unchanged. Failed prepare clears pending output; a mismatched presentation cannot commit. `hdr10` output fields are zero. The snapshot target/container use BT.709 and gamma 2.2 or 2.4. Custom gamma uses the gamma 2.4 base followed by the validated `policy.sdr.gamma` exponent inside the selected legal signal range; consumers must retain the policy gamma rather than infer arbitrary custom gamma from the transfer enum. Resolve supports 8–16 native bits with dithering.

DV reconstruction retains RPU source luminance bounds and L1 maximum/average luminance for SDR tone mapping. L1 minimum and L6 are not consumed by this mapping and must not be reported as applied. HDR10+ scene MaxSCL/average already supplied in `pl_frame.color.hdr` guide the default libplacebo tone mapping; this does not attest application of an authored HDR10+ Bezier curve or saturation weight. The adapter owns original metadata capture and applied-metadata reporting.

## Plain HLG to DV Reference

The existing `cb1_hdr10_ai_submit` and `dvbridge_render_hdr10_ai_rgb` / packed / overlay calls accept original HLG BT.2020 pictures. Rendering accepts HLG only in Standard/Reference mode. Actual DV carrying RPU, including an HLG base, remains on its DV reconstruction route and is rejected by plain-HLG ingress.

`cb1_hlg_reference_color` pins a BT.2100 reference display at 1000 nits, zero black and system gamma 1.2. libplacebo performs inverse HLG OETF and the luminance-dependent BT.2020 OOTF, then encodes PQ. Model analysis normalizes the complete source before shared extrema/statistics/quantiles and progressive preview downsampling. Source-plane PQ-only shortcuts are disabled for HLG. Movie rendering independently performs the same reference conversion from the original HLG source. HLG values are never merely relabeled as PQ. Model prefix, asynchronous identity, temporal tracking and retirement remain shared. Generated metadata contains no authored L2/L8 trims.

## Qualification

`tests/sdr_render.c` covers presets/custom validation, BT.709 transfer, HDR10+ scene-statistics influence, custom gamma in limited range, independent DV reconstruction equivalence with a non-neutral FEL, HLG-base DV source tags, identity rejection, mismatched FEL timestamps, finite pixels and malformed source luminance.

`tests/hlg_reference.c` checks the analytic neutral 75% HLG reference against both model ingress and movie PQ output, progressive preview alias suppression, a real 25-frame asynchronous model prefix, original-HLG admission, Adaptive rejection and absence of synthetic L2/L8.

Run the complete standalone CMake/CTest suite with the matched FFmpeg/libplacebo/LightGBM prefixes and private reference/model fixtures described by `tests/CMakeLists.txt`. Set `PKG_CONFIG_PATH`, `CMAKE_PREFIX_PATH` and the shared-library path to those same prefixes for subprocess checks. Software GLES qualification is not physical playback qualification.

A reproducible configured-tree invocation (prefix/fixture variables refer to the matched private build inputs):

```sh
PKG_CONFIG_PATH="$FFMPEG_PREFIX/lib/pkgconfig:$PLACEBO_PREFIX/lib/pkgconfig" \
cmake -S CB1 -B "$ENGINE_BUILD" \
  -DCB1_BUILD_TESTS=ON -DCB1_ENABLE_HDR10_AI=ON \
  -DCMAKE_PREFIX_PATH="$FFMPEG_PREFIX;$PLACEBO_PREFIX;$LIGHTGBM_PREFIX" \
  -DCB1_FFMPEG_SOURCE="$FFMPEG_SOURCE" \
  -DCB1_FFMPEG_STOCK_SOURCE="$STOCK_FFMPEG_SOURCE" \
  -DCB1_SWS_PRODUCER_SOURCE="$FFMPEG_SOURCE" \
  -DCB1_CUMULATIVE_SOURCE="$HISTORICAL_SOURCE" \
  -DCB1_REFERENCE="$NATIVE_REFERENCE" -DCB1_SOURCE_COMMIT="$SOURCE_COMMIT" \
  -DCB1_L1L3_BUNDLE_CONTRACT="$ORACLE_CONTRACT" \
  -DCB1_L1L3_TEST_BUNDLE="$MODEL_BUNDLE" \
  -DCB1_LIGHTGBM_INCLUDE_DIR="$LIGHTGBM_PREFIX/include" \
  -DCB1_LIGHTGBM_LIBRARY="$LIGHTGBM_PREFIX/lib/lib_lightgbm.so"
cmake --build "$ENGINE_BUILD" -j8
PKG_CONFIG_PATH="$FFMPEG_PREFIX/lib/pkgconfig:$PLACEBO_PREFIX/lib/pkgconfig" \
LD_LIBRARY_PATH="$FFMPEG_PREFIX/lib:$PLACEBO_PREFIX/lib:$LIGHTGBM_PREFIX/lib" \
LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe EGL_PLATFORM=surfaceless \
ctest --test-dir "$ENGINE_BUILD" -j4 --output-on-failure
```

Final standalone qualification: all 257 registered tests completed with zero failures; 234 passed and 23 returned their explicit capability skip. Total wall time was 78.80 seconds. GLES shader/image/identity/lifecycle tests ran on llvmpipe (OpenGL ES 3.2, Mesa 25.2.8); the skipped GUI/packed-transport/subgroup and VA/VPP cases are not claimed as physical GPU coverage. The standalone no-Kodi build, original source provenance/privacy checks, stock-header rejection, frozen native replay and matched AI inference checks passed. `git diff --check -- CB1` passed.
