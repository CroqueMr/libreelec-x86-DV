# GBM display colour settings

Generic follows Kodi PRs [30099](https://github.com/xbmc/xbmc/pull/30099)
and [30192](https://github.com/xbmc/xbmc/pull/30192), by smp79. The backport is
pinned to `9fcc80c946fc94f8fdcbe899a15baa0453bd6d63` and
`6cc7650a603fc06992326742def234c27728e310`; the range dependency is applied
once. These are unmerged upstream proposals, adapted to the pinned Kodi base.

The normal display settings offer:

- **Colour range:** Auto, Full or Limited. The previous limited-range setting
  is migrated once. A driver conversion and a shader conversion must not both
  compress the same image. Software conversion remains available when the
  connector cannot perform the requested conversion.
- **Colour format:** Auto, RGB, YCbCr 4:4:4, 4:2:2, 4:2:0 or Adaptive, only
  when the driver exposes the writable connector property. Adaptive considers
  content depth and link constraints and has bounded fallback attempts.
- **Maximum bit depth:** Auto or a value within the driver's reported limits.
  Auto restores the captured driver default. This sets a ceiling; it does not
  assert that every frame or physical link operates at that depth.

The kernel remains 7.2.6. The generic `color format` interface requires newer
driver support, so this setting is hidden when absent; adding the menu does
not add that interface to older Intel, AMD or NVIDIA drivers. Range and bit
depth controls are likewise subject to connector capabilities. DP/USB-C and
HDMI are not assumed to have identical bandwidth or FRL capabilities.

CB1's dedicated Dolby Vision and HDR10 output owns its own connector tuple.
Ordinary display preferences are saved before entering that output and are
deferred while it is active. Accepted ordinary output is restored before
pending preferences resume. This includes failed preparation and delayed
stop/recovery paths; native Dolby Vision retains its required 8-bit transport.

Native owner tests cover accepted and rejected requests, retry limits, missing
properties, format/range combinations and CB1 restoration. Compilation and
these tests do not qualify a particular GPU, cable, television or receiver.
