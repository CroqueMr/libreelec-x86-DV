# HDR10+ pacing on Intel N100

## Playback result

Hardware: CWWK x86-P5 (Intel N100), Samsung S95B. Source: Dolby Vision
Profile 8 at 23.976 fps. Output: 3840x2160 at 23.976 Hz, 30 bits per pixel.
Baseline: RC3 Preview Update6 (`c91b115f35-backlog-77c621cce6`). The PACING1
test image replaced only Kodi's executable, adding the curve optimization
and bounded diagnostic logging; the kernel and remaining system files were
unchanged. The diagnostic logging is not included in this change.

Each capture ran for 20 seconds. Intervals below are between
`drm_vblank_event_delivered` events on the active CRTC.

| Playback path | Display completions | Mean interval | Longest interval | Double-refresh intervals |
| --- | ---: | ---: | ---: | ---: |
| Native Kodi, baseline | 480 | 41.708 ms | 41.911 ms | 0 |
| HDR10 Rendering, baseline | 479 | 41.708 ms | 41.907 ms | 0 |
| HDR10+ Rendering, baseline | 449 | 44.501 ms | 83.601 ms | 30 |
| HDR10+ Rendering, PACING1 | 480 | 41.709 ms | 41.901 ms | 0 |

The baseline HDR10+ capture had 418 single-refresh intervals and 30
double-refresh intervals. PACING1 had 479 consecutive single-refresh
intervals (minimum 41.513 ms). Kodi's dropped/skipped counters did not
increase during either steady HDR10+ capture, despite the baseline's uneven
display cadence. The tester confirmed normal-looking motion and that the
TV continued to report HDR10+ with PACING1.

These events measure DRM commit-completion cadence. They do not establish
unique picture identity or directly measure the physical HDMI signal.
This is a successful test of the affected scene, not an all-content guarantee.

## Diagnosis and change

CPU sampling attributed approximately 40% of sampled cycles to candidate
curve error validation, including repeated PQ power calculations. The
candidate error is a running maximum over 4,097 samples. A candidate can
stop once its error cannot beat the current best, or strictly exceeds the
existing acceptance threshold of `2/1023` PQ. A candidate that can be
returned still completes the validation grid and reports its exact error.
The threshold comparison is strictly greater: equality remains acceptable.

The optimization preserves curve selection, quantization, the validation
grid and the acceptance threshold. HDR10+ metadata and packet transmission
remain enabled.

## Validation

- Compared baseline and optimized fits across 480 synthetic monotonic
  curve/target combinations: identical accept/reject decisions, output
  fields and maximum-error double bits, including unchanged output on failure.
- The same comparison passed on the N100 using the matching GCC 16 toolchain.
  A 30-fit identity-curve microbenchmark averaged 5.321 ms before and
  2.332 ms after. This benchmark is not a measurement of total frame cost.
- AddressSanitizer and UndefinedBehaviorSanitizer comparison checks passed.
- The engine curve test passed on the N100: accuracy, monotonicity, invalid
  inputs and independent packet receive-side expansion. The regression
  assertions also check the reported maximum PQ error against packet output
  over the complete validation grid, and unchanged output after rejection.
- The full modified Kodi build completed, booted on the N100 and produced
  the PACING1 capture above.

## Capture method

In an isolated tracefs instance, enable `i915/intel_pipe_update_start`,
`i915/intel_pipe_update_end`, `i915/intel_crtc_flip_done` and
`drm/drm_vblank_event_delivered`; clear the buffer, record for 20 seconds,
then stop tracing and disable those events. `intel_crtc_flip_done` did not
produce events on this build. Count the active CRTC's delivery events,
compare consecutive timestamps and sequence numbers, and corroborate
sequence increments with the pipe-update events. Leave playback menus
closed and confirm normal playback speed and source frame rate in Kodi's
health diagnostics.

All trace events were disabled after capture. Media titles, file paths,
network addresses and private playback logs are omitted from this report.
