# Versions

| Component | Version / revision |
| --- | --- |
| Release | R1.0.0 Beta1, tag `R1.0.0-Beta1` |
| LibreELEC | 13.0-devel, `3de4708704041ead8ae1531092efb7ea5da9d355` |
| Kodi | 22.0 RC1, `28ea2eac1eb7af8fdcbd2672d933ce87f594be79` |
| Linux | 7.2.6 |
| FFmpeg | 9.0, matched CB1 patches |
| libplacebo | 7.372.0, `e2972fdd09adacd383656738d7d280f0cd84a761`, matched CB1 patches |
| Mesa | 26.2.3, unmodified |
| Intel Media Driver | 26.3.5, unmodified |
| libva | 2.24.1, unmodified |
| CB1 | Engine 0.1, bundled in this release |

`config/cb1-source-lock.json` identifies the exact staged sources.
`config/cb1-patch-index.json` describes each patch and modified file.
Circuit versions are defined by CB1 and displayed by Kodi.

## Repository management

- `CB1/` owns the engine and FFmpeg/libplacebo patches.
- LibreELEC owns Linux/Kodi integration, recipes and images in this repository.
- Engine changes require updated source hashes and image qualification.
- Driver/UI-only changes do not change rendering circuit versions.
- Upstream updates are reviewed separately; CB1 never follows a floating branch.

The release tag identifies the matching engine, model and integration sources.
LibreELEC ancestry and the previous repository history are retained.
