# Native DV output and paused HDR10/AI transitions

## Approved scope

Correct two reproduced failures on the current Preview G candidate: Dolby Vision
activation when Kodi selects native 1080p HDMI output, and repeated native HDR10
to/from Dolby Vision AI Reference changes while paused on N100. Validate both on
N100 and AMD 3200U, without publication.

## Approach

Follow Kodi's existing resolution, whitelist, view, GBM/EGL and renderer lifecycle
owners. Trace the actual request and fix the first inconsistent boundary. Reuse
the original helpers and synchronization; no alternate output selector or scaler.
Preserve kernel tunnel-integrity checks, source reconstruction, Master pixels and
metadata for the same output geometry, native filter kernels and all AI inference.

For the paused transition, retain the original decoded picture and use Kodi's
normal reconfiguration/render preparation so a mode change can complete without
resuming the film. Diagnose first; no arbitrary sleep, offset, longer fallback
deadline or extra frame queue.

## Alternatives excluded

Forcing UHD instead of Kodi's selected output would hide the failure. Weakening
driver validation could corrupt the tunnel. A second scaler or output path would
duplicate Kodi. None is authorized.

## Success and non-goals

Native 1080p and UHD output both activate the selected DV mode without unexpected
fallback or stall. Repeated paused native-HDR10/AI changes settle, preserve pause
and zoom, then resume and stop cleanly. The same files remain valid on both GPUs.
Master comparison witnesses remain exact, and existing UHD cadence is retained.
1080p performance optimization beyond these correctness fixes is not included.
