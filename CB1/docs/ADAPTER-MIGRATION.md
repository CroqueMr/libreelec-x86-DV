# Adapter migration status

Local Beta5 qualification only. The migration remains incomplete.

| Portion | Current decision | Preserved contract |
| --- | --- | --- |
| Kodi `DVBridgeState.cpp/.h` | Replacement GPL-2.0-or-later transaction and property-plan implementation | Public API, capture/rejection decisions, required/optional properties, enum selection, complete stage/restore order, blob ownership and foreign-VSIF rejection |
| libplacebo `9915-hdr10-linear-conversion` additions | Original CB1 contribution under owner's GPL-2.0-or-later grant; upstream LGPL code/notices retained | Patch implementation bytes unchanged; no shader, ABI or default change |
| libplacebo `9916-fel-filter` additions | Original CB1 filter/reference adapter under the same grant; upstream LGPL retained | Patch implementation bytes unchanged; integer-reference shader already retains its LGPL notice |
| libplacebo `9913-processing` | Still GPL-3.0-or-later pending replacement of attributed processing portions | Do not relabel YBLOD adaptations through the original-code grant |
| Renderer source-space GUI/fused colour adapter | Still GPL-3.0-only pending independent replacement | Replaced carrier kernels do not clear the retained surrounding implementation |
| Other Kodi integration, import and FEL units | Still under their existing notices pending portion-level review | No blanket grant applied to Hades or other third-party material |

The output-state replacement implements the existing property contract as
ordered data and a snapshot reader using Kodi/libdrm APIs. Successful capture
publishes owned snapshots only after plane validation. Failure destroys temporary
blobs without changing the captured state. Staging attempts every saved property;
restore uses cloned original blobs. Display matrices, movie samples, transport
payload and driver selection rules are unchanged.

NVIDIA property names, blob types and S31.32 neutral factors are public in the
MIT-licensed [615.71.09 DRM interface](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.71.09/kernel-open/nvidia-drm/nvidia-drm-drv.c)
and [property-state implementation](https://github.com/NVIDIA/open-gpu-kernel-modules/blob/615.71.09/kernel-open/nvidia-drm/nvidia-drm-crtc.c).
Only the interface contract is consumed; no NVIDIA kernel implementation is copied.
The existing Kodi DRM blob utility and upstream notices are retained.

The prior output adapter was adapted from LibreELEC Hades RC2
`69fc36199f0d5f5d1e5bb4d42f45656e256a6e35`. That historical attribution is not
removed by replacement and does not authorize unrelated Hades code.

## Differential verification

```sh
python3 CB1/tools/compare_beta5_output.py --baseline /path/to/frozen/Beta5/repository
```

The standalone probe compiles the old and new output adapters separately and
compares 195 complete API traces. Cases include both backends, kernel preference,
absent optional/required properties, failed enum/blob/plane queries, owned and
foreign VSIF blobs, partial staging failure, exact restoration and resource cleanup.
A deliberate wrong-enumeration mutation is rejected. Enum names/values, unique
blob identities/payloads and resource creation/destruction are traced separately.
DRM boundary doubles do not qualify a
real driver, HDMI link or GPU. Historical oracle sources are not linked into Kodi.

For the two grant-only libplacebo patches, compare the full patch text from the
first `diff --git` line against normal Beta5. Both are identical; modified-source
hashes and processing ABI 9 remain unchanged. The combined modified library still
contains unresolved GPLv3 additions.

## Dependency qualification

The offline comparisons use a new library built from the published normal-Beta5
libplacebo component archive, SHA-256
`1a42b5d62a3d84740fb3923901f867fc8acc5cd2b3ea08c1b20a780424dbf087`.
Every locked modified-source hash matches. Frozen Beta5 and the candidate use
that same rebuilt library; dependency hashes are not relaxed.

Replaying the current upstream archive and patch recipe does not reproduce that
published source snapshot: paired-row contract-2 reconstruction additions are
missing from the replay. This pre-existing recipe/snapshot gap remains open.
No unrelated reconstruction change or new dependency pin is included here.
Complete image reproducibility is not established by these engine tests.
