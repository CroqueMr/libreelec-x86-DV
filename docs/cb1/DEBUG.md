# Beta5 Debug

Debug adds strict Master Reference IPT, bounded diagnostic details and a driver-profile selector. Normal Beta5 does not compile the IPT circuit or Debug controls.

## Driver profiles

In **Settings > System > Logging**, enable **Use standard LibreELEC drivers (reboot required)**, then restart. Disable it and restart to return to the modified drivers. No driver is replaced while running.

Both profiles use the same pinned Linux version, Kodi, CB1 and Mesa. The standard profile keeps ordinary LibreELEC patches and excludes the listed custom graphics patches. It is not a complete vanilla Kodi build. Dolby Vision output may be unavailable with standard drivers.

The control is disabled if a matched pair, valid boot configuration or sufficient boot-partition space is missing. Selection verifies both payload pairs before updating boot entries. The active and requested profiles, kernel version and payload identities are logged automatically.

Install Debug from its complete disk image first. Use paired Debug TAR updates only after that installation. An older updater cannot enforce the new safeguards. The new updater refuses mixed normal/Debug conversions and incomplete payloads. Updates retain LibreELEC's sequential writes, not power-loss-safe A/B recovery.

## Building

Build separate Debug components with `CB1_DEBUG=yes` and `CB1_DRIVER_PROFILE=modified` or `standard`, using the native `make system` target. Preserve each resulting kernel, SYSTEM and actual applied-patch receipts. The recipe cache includes the variant/profile selection.

Package the independently recorded build evidence with:

```sh
python3 scripts/cb1-debug-profiles.py --evidence evidence.json --output paired
```

The helper validates pinned sources/patches, matching module versions and identical non-module SYSTEM contents. Its `--help` describes the evidence schema. It does not build a kernel or synthesize provenance.

For final native `make release` or `make image`, select the modified profile, provide `CB1_DEBUG_PROFILES_DIR` and retain the exact prepared modified `.kernel`/`.system` files in the native target directory. Packaging checks these files against the pair instead of regenerating SYSTEM. NOOBS is not supported for paired Debug.

The disk image and installer check required boot-partition capacity. Existing partitions are not resized automatically. Both profiles preserve an entry returning to modified drivers.

## Diagnostics and skins

Debug exposes bounded diagnostic details without enabling Kodi's global debug log. Master Reference IPT remains strict, with no Fast rendering or silent rendering fallback.

Enhanced Player information uses shared Kodi resources and named native fonts. Disabling it restores the active skin's native dialog. Quick rendering switch retains the active skin's selector presentation; no third-party skin is bundled.
