# Retry an unaccepted SDR output restoration

Scope approved for direct execution: fix stop/relaunch signaling only, with RC1
frozen at `f5002ad86080082a4eb989729419dba389c682df`. No publication or installation.

## Approach

Retain SDR intent at the existing DRM atomic boundary until a real commit accepts
the clear. Re-stage static HDR metadata and the intended colorimetry on retry:
Default for the GUI, or the new SDR movie's primaries if playback restarted. Do not
fall back to the preceding HDR request and report that as a successful SDR reset.
A new admitted HDR picture supersedes this intent; a new SDR picture does not.
Use Kodi's existing dirty-GUI/presentation loop, not timers or display resets.

The CB1 stop transaction retains its ordinary successor after a rejected commit
and re-stages the restoration on the next GUI frame. If recovery has already
relinquished CB1 ownership, stop explicitly requests the native SDR GUI state.
Other transition policies remain unchanged.

Alternatives rejected: retaining all failed atomic properties would replay stale
framebuffers/fences; restarting the display or adding sleeps would mask the
rejected commit and introduce unnecessary visible transitions.

## Invariants

- No movie shaders, filtering, pixel buffers, DV RPU or HDR movie metadata changes.
- No new settings, dependencies, threads or retry queue.
- Failed property staging, test commits and real commits cannot acknowledge SDR.
- A successful retry clears the pending state. Repeated stop is idempotent.
- No retry may replace signaling for a newly admitted HDR movie.
- The reporter's exact cause remains unconfirmed without their log/build version.
