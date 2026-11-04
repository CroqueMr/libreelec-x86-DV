# R1.0.0 RC3 build

Requires a Linux x86-64 host, LibreELEC build dependencies and the complete source tree.

Published image identity: `DV-R1.0.0-RC3`. Rebuild the published image from a clean
checkout of `R1.0.0-RC3` (`6797dfb4c7c2669a1d9ccb021fffae91375380f6`), not an
arbitrary default-branch snapshot. The release source configuration uses the
logical ID `R1.0.0-RC3`; use the published [RC3 release](https://github.com/CroqueMr/libreelec-x86-DV/releases/tag/R1.0.0-RC3)
for its attached image and corresponding-source archives.

```sh
python3 CB1/tools/verify.py
python3 scripts/cb1-stage.py
CB1_HDR10_AI=yes PROJECT=Generic ARCH=x86_64 OFFICIAL=no make image
```

Staging verifies and copies the bundled CB1 sources, model and matched dependency
patches into LibreELEC's native package directories. Do not mix headers or libraries
from another version. Native recipes download the pinned upstream archives and apply
the recorded patches; this tree does not use Beta4's frozen pre-patched archives.

Supported Intel/AMD integrated and dedicated GPUs, NVIDIA GeForce GPUs and AMD
HDMI 3D use one Generic image. The image includes matched NVIDIA R615 and R580
modules, firmware and userspace; the appropriate branch is selected at boot.

The AI model under `CB1/models/l1l3/` is required for the AI circuits. Training data,
movies, extracted frames and private oracle fixtures are not release inputs.

For regression checks, use the matched-source preparation in
`.github/scripts/prepare-test-sources.sh` or set the dependency/source paths consumed
by `tests/cb1`. Engine test requirements are listed in [CB1 build](../../CB1/docs/BUILD.md).
Hardware-dependent checks require the corresponding GPU and display route.
The CI preparation exports the matching Kodi archive as `KODI_UPSTREAM_ARCHIVE`;
native display tests also require the host libdrm development headers.

Component pins are in [versions](VERSIONS.md), `config/cb1-source-lock.json` and
`CB1/config/dependencies.json`. The model contract is in
`CB1/config/hdr10-ai-dependencies.json`. Runtime assets and applicable notices must
remain in corresponding-source exports. Rebuild hashes can vary with the toolchain,
timestamps and build paths.
