# Default playback and Player information refinement

Approved by the user on 2026-11-10; baseline source549c70760ed7cd6afbd83a854011fd1bd40402e0. This task continues locally; no release/publication is authorized.

## Intent

Restore reliable CB1/native Kodi handoffs, make stored source defaults independent from live choices, and refine the current information panel without moving its existing blocks. Prefer native Kodi facilities and existing owners. No new engine, dependency or layered workaround.

## Binding behavior

- A live change through Kodi default must not poison later playback in the same process. Preserve GPU retirement, actual atomic-commit acknowledgement and strict scanout validation. Investigate initial invalid request separately from a retained failure after successful recovery; never clear a failure just because a new file opens.
- Persist existing per-source choices as Dolby Vision default playback, HDR10 default playback, HDR10+ default playback, HLG default playback. DV includes HLG-based DV with RPU. Show the stored choice on the right, including the DV method distinction.
- New file/reopen/restart uses that source default. Live menu changes are playback-session overrides only; seek/pause/decoder reopen retain the choice. They never save a last-used circuit over the default. Editing a default while a file is playing affects the next file; non-selector tuning retains its existing live behavior. Avoid a duplicate settings database or another preference service.
- No automatic substitution to another CB1 circuit when the requested circuit is unavailable. Show a clear reason. Pending preparation remains pending; selected Kodi default retains native behavior. Native shutdown/GUI restoration is not a circuit fallback.
- HDR-to-DV and HLG-to-DV AI circuit label is exactly Dolby Vision rendering (AI), in the relevant selection/panel. Do not rename authored DV Reference/Master or HDR10 Rendering Reference.
- Prefix dependent settings with ' - ', as CM4 does. Remove Reference only from dependent labels: HDR10 Rendering Reference peak brightness becomes ' - HDR10 rendering peak brightness'. Keep the circuit name. SDR rendering target becomes HDR/DV to SDR target, applies only to HDR10/HDR10+/DV conversion, not native SDR.
- Remove user-visible Optimized GUI rendering; enable the existing optimization automatically only where its current capability/safety gates permit. No native Kodi optimization or output-circuit substitution. Validate actual GUI correctness before treating this as ready.
- Remove Use encoded frame as Dolby Vision active area; respect authored L5. Ignore obsolete persisted true values rather than retaining a hidden global override. Do not infer stale margins from aspect ratio or change film geometry.

## Panel identity and layout

Keep CURRENT block positions, column membership and ordering. Latest user correction explicitly overrides any interpretation that the PR layout should relocate information. Retain Input / Processing / Output, detailed source metadata in Processing and the existing footer location.

Reuse PR92 rounded surface/border/form as closely as possible without moving blocks. Existing cb1-glass/card/chip textures are available; cb1-glass center alpha is255. Preserve current bright green for active CB1 text and vivid accents. Used metadata stays neutral/opaque; unused elements hidden; native Kodi has no active-CB1 green. Keep removals Also carried, audio Presentation, Language and Subtitles. O overlay only, no extra popup/paging/up-down/scroll/wrap. Real HDR10plus-to-DV apparent transparency must be assessed through composition as well as skin alpha; do not assume an FF text color is enough.

## Boundaries

No PR101 DVD work, PR100 desktopGL port, new HDR60 optimization, AMD hardware work (offline), Support build, release/tag/assets/staging/publication. Prior N1004K60 HDR10/DV-to-SDR limits remain documented failures. Old accepted software/artifact/physical evidence and closed private-harness caps remain historical and unchanged. New code has its own focused tests; no weakened renderer/receiver/counter gates or fake optical claims.

## Validation

Use real existing producer/caller bodies for handoff/default-state regressions, GLES pixel tests for composition, static layout/copy checks for precise UI requirements, patch replay and native translation-unit compilation. Run the matched full suite once after integration; preserve zero skips locally or explain actual unavailable dependencies. Any new local image gets exact source/payload/boot identity and bounded owned hardware checks of the changed cases. No full18 rerun merely because labels changed; broaden only if an actual shared-rendering concern warrants it. Original losses stay losses. Final original Astra xhigh review covers correctness AND simplicity; no automatic release action follows.
