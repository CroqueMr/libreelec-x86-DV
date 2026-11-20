# libreelec-CB1 source history

[Original source](https://github.com/LibreELEC/LibreELEC.tv) · [Image and releases](https://github.com/CroqueMr/libreelec-CB1)

The tables record historical source deltas, original evidence, and category. LibreELEC selects tested source commits through its recipes.
Early rebases and inconsistent surviving patch stacks can leave intermediate snapshots unverified.

## Related repositories

- [FFmpeg](https://github.com/CroqueMr/FFmpeg)
- [xbmc](https://github.com/CroqueMr/xbmc)
- [CB1](https://github.com/CroqueMr/CB1)
- [libplacebo](https://github.com/CroqueMr/libplacebo)
- [libbluray-cb1](https://github.com/CroqueMr/libbluray-cb1)
- [linux](https://github.com/CroqueMr/linux)
- [open-gpu-kernel-modules](https://github.com/CroqueMr/open-gpu-kernel-modules)
- [egl-gbm](https://github.com/CroqueMr/egl-gbm)

## Merged source pull requests

| Change | Category | Source commit | History branch |
|---|---|---|---|
| [Record platform kernel and NVIDIA compatibility](https://github.com/CroqueMr/libreelec-CB1/pull/271) | DV Patch | 4a74a080696b | codex/1.1-history-integration |
| [Record the FFmpeg package and decoder integration](https://github.com/CroqueMr/libreelec-CB1/pull/272) | DV Patch | 965ce1a6156a | codex/1.1-history-integration |
| [Record the Kodi package, UI and playback integration](https://github.com/CroqueMr/libreelec-CB1/pull/273) | DV Patch | d9526b4a6f33 | codex/1.1-history-integration |
| [Record the libplacebo package and shader integration](https://github.com/CroqueMr/libreelec-CB1/pull/274) | DV Patch | 6dba063fabcf | codex/1.1-history-integration |
| [Record the original CB1 engine and validation assets](https://github.com/CroqueMr/libreelec-CB1/pull/275) | DV Patch | 824a0b05a527 | codex/1.1-history-integration |
| [Retain the RC3 staged engine and model inputs for legacy variants](https://github.com/CroqueMr/libreelec-CB1/pull/276) | DV Patch | f0e457ea8adc | codex/1.1-history-integration |
| [Record libbluray navigation, Java and UDF integration](https://github.com/CroqueMr/libreelec-CB1/pull/277) | Upstream Fix | f8780608986a | codex/1.1-history-integration |
| [Record project documentation and provenance](https://github.com/CroqueMr/libreelec-CB1/pull/278) | Upstream Fix | a83eea527caf | codex/1.1-history-integration |
| [Record remaining LibreELEC image packaging and configuration](https://github.com/CroqueMr/libreelec-CB1/pull/279) | Upstream Fix | 705d9d1e9bf9 | codex/1.1-history-integration |
| [Record the combined integration and regression suite](https://github.com/CroqueMr/libreelec-CB1/pull/280) | Upstream Fix | c8a71952c05e | codex/1.1-history-integration |
| [Record the source locks and build verification](https://github.com/CroqueMr/libreelec-CB1/pull/281) | Upstream Fix | 886bb3419e40 | codex/1.1-history-integration |
| [Apply the FFmpeg 9.0.2 integration and the final CI fixture updates](https://github.com/CroqueMr/libreelec-CB1/pull/282) | Upstream Fix | 7d4e0d861b06 | codex/1.1-history-integration |

The 12 source replay PRs reproduce the exact integration tree dd60140119d9f00baad665d44e6aa58e6ac45ca1.

## Upstream preparation

Propose general correctness fixes and performance improvements against the owning project. Separate Dolby Vision policy from generic API changes and retain the original attribution.
See the linked PRs for their DV Patch, Upstream Fix or Performance Improvement category.

## wlroots

The [wlroots source mirror](https://github.com/CroqueMr/wlroots-cb1) preserves the official source and the [Generic Wayland DRM fix](https://github.com/CroqueMr/wlroots-cb1/pull/1).
