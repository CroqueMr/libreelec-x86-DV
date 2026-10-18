# CB1-L1L3 0.1

LightGBM model for HDR10-to-Dolby Vision L1/L3 estimation. Reference AI and
Adaptive HDR Mapping AI use the same model. It does not supply authored creative
trims or replace the original Dolby Vision metadata of a DV source.

| Property | Value |
| --- | --- |
| Backend | LightGBM 4.7.0, native C API |
| Inputs | 222 normalized features |
| Outputs | Six residual predictions for L1 and paired L1/L3 |
| Strength | 0.75 |
| Runtime assets | `data/` |
| Native integrity contract | `contract/cb1_l1l3_bundle.h` |

The bundle is the exact runtime artifact. File hashes are pinned in
`config/hdr10-ai-dependencies.json` and checked by `tools/verify.py`.
No training clips, extracted frames or training dataset are included.

Model assets carry a GPL-3.0-or-later declaration. LightGBM itself is MIT.
The dependency lock still records `redistribution_cleared: false`; confirmation
of model provenance and redistribution rights remains unresolved. A matching
bundle hash is an integrity check, not that confirmation.
