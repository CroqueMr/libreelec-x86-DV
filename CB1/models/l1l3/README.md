# CB1-L1L3 0.1

LightGBM model for HDR10-to-Dolby Vision L1/L3 estimation. Reference, Natural
and Signature use the same model.

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

Model assets are distributed under CB1's GPLv3 terms. LightGBM itself is MIT.
