# RC1 diagnostics and Beta5 comparison

## Intent

Freeze the Preview2-C candidate plus bounded startup diagnostics as
`DV-R1.0.0-RC1`, build the complete image and compare it with the published
normal Beta5 image on the Intel N100 and AMD Ryzen 3 3200U.

## Scope and approach

Reuse native FFmpeg MOV association, Kodi demux inventory and the current
diagnostic session. Record HEVC codec tags, declared dependencies and rejection
facts without URLs or filenames. Decoder startup records BL decoded, EL submitted,
EL decoded and FEL paired once per codec open; first presentation uses the
existing accepted-commit owner. No per-frame messages, new polling or decode,
rendering, timing, driver, pixel, metadata or fallback changes.

Alternative of adding a new diagnostic framework is rejected: the shared logger
already bounds lines and handles waits/failures. The user approved direct
implementation of the existing proposal. Keep Preview2-A/C commits and existing
archives unchanged. GitHub tag naming is `R1.0.0-RC1`; build/image naming includes
`DV-R1.0.0-RC1`. Do not publish or message issues during this work.

## Benchmark

Compare complete, hash-identified normal Beta5 and RC1 images. Reuse the native
updater, existing HDMI/fence observer and paired local media. Preserve boot
payload recovery and user settings. Do not force clocks. Use async On. Beta5
uses Fast On except strict Master; RC1 uses its intrinsic circuit policies and
disables automatic Master-to-Standard fallback during measurements.

4K and 1080p mean source dimensions, with the same 4K HDMI output. Use Kodi
Normal view and assert zoom=1.0, pixelratio=1.0 and verticalshift=0 before and
after every measured window. Restore original per-source views/settings.

Cover compatible Standard, Master, Adaptive, DV-to-HDR10 Basic/Expert,
HDR10-to-DV Reference AI/Adaptive AI, native and fallback paths. Explicitly mark
HDR10+ output unavailable if the sink does not advertise it. Do not label its
HDR10 fallback as real HDR10+ qualification. Avoid an incompatible source/mode
Cartesian product.

Master and Standard additionally use P7 FEL30, P5 30fps and Gemini Man 59.94fps,
with and without the native playback progress/controls bar. Do not open Player
information for the no-GUI condition. Preserve each fixture's actual profile,
rate, layers and hash; identify any derived test fixture rather than claiming it
is original media.

Use three steady 20-second samples per cell after startup settling, at identical
passages for both builds. Where the finite source cannot cover this, use repeat
playback at the same passage, not an undocumented loop or alias. Stop a grossly
failing cell early and retain its failure, never substitute it with a better run.

## Metrics and validity

- CPU busiest logical core: mean of per-second busiest-core utilization from
  `/proc/stat`. CPU total: machine-wide busy share normalized across all logical
  CPUs. Also retain Kodi CPU as equivalent one-core percentage for diagnosis.
- GPU rendering-engine mean busy share from the same native per-process DRM
  counters on both builds. Retain decoder counters separately; do not sum
  overlapping engines or call this whole-GPU occupancy.
- Exact native Kodi dropped/skipped counter delta where observable, separately
  from accepted-frame cadence and missed presentation intervals. Unknown is not
  zero. Resolve counter access before launching the long matrix.
- Mean headroom: GPU-ready-to-presentation-deadline margin in milliseconds from
  matched native fence/presentation evidence. Keep P01/minimum too. This is not
  source frame period minus GPU utilization, and is not an FPS-only estimate.
- Verify source, requested/effective route, physical output, clock/rate, zoom,
  complete trace and unchanged binaries. Invalid windows remain visible.

Reuse existing tested instrumentation. Do not introduce a new renderer or
permanent GUI dependency for measurement. Keep generated evidence in one task
directory, preserve raw observations and compact aggregate results. TV is used
only as needed for valid HDMI measurements. Restore RC1 and user settings on
both hosts after the comparison. No performance or stability success claim
without measured evidence.
