# Preview F: native-resolution rendering

Status: proposed design, awaiting approval. No rendering cleanup implemented yet.

## Intent

Replace accumulated resolution-specific routing with one spatial contract per existing rendering mode. Process the decoded picture on its source grid, then fit it to the output once, as late as possible. 1080p, 1440p, cropped pictures and 4K use the same mode algorithm, precision contract and protection rules.

"Fresh base" means removing obsolete spatial orchestration, not rewriting the validated Dolby reconstruction, color math, tone curves, AI model or HDMI protocol.

## Preserved baseline

- Source checkpoint: ac554732636da0bebc5d29d816e3b13ae2c2c145.
- Frozen branch: checkpoint/rc1-preview-e-single-recipe-20261026.
- New branch: candidate/rc1-preview-f-native-resolution.
- Existing Preview E archives remain retained and hash-checked. They precede the Fast cleanup; the source checkpoint includes it. Do not describe these as the same complete image.
- Existing audit: work/rc1-a-f-20261024/1080P-AUDIT.md outside this repository.
- No publication. No machine changes during design.

## Approach selected in the conversation

Rebuild the spatial orchestration using existing rendering primitives and mode algorithms.

Alternatives considered:
1. More isolated 1080p fixes: rejected, retains duplicate paths and does not cover arbitrary source dimensions.
2. New rendering engine and algorithms: rejected, unnecessary scope and fidelity risk.
3. Common source-grid treatment and late output stage: selected. Preserves established processing while replacing the problematic boundaries between passes.

## Scope and exclusions

In scope: Standard, Master Reference including P5, authored Adaptive, DV-to-HDR10 Basic/Expert, existing DV-to-HDR10+ output, HDR10-to-DV Reference AI and Adaptive AI. Retain the existing Master IPT transport choice without reopening its algorithm or performance target. It must not break when common code changes.

Out of scope: new profiles or quality settings, Fast/Auto controls, new reconstruction or model, driver/kernel changes, audio, codec/container demux changes, HDR10-to-HDR10+ features, vanilla/fallback rendering, new queues/schedulers, forced clocks or full generic render graphs.

Master-to-Standard performance recovery remains the existing explicit option, default Off. Qualification disables it and checks the actual output circuit. A fallback is not a successful performance result.

## Spatial contract

Distinguish:
- decoded source dimensions and source crop;
- each input plane's actual dimensions, subsampling and chroma siting;
- source active area from L5;
- final displayed rectangle, aspect ratio and orientation;
- physical output/carrier dimensions.

Reuse the existing geometry and plane contracts. Add fields or a small internal helper only if the current structures cannot express a demonstrated requirement. Do not create a second public render API for each resolution.

Logical order:
1. Decode/import existing source planes without a full-picture enlargement.
2. Reconstruct the selected DV representation on the base-layer source grid, including BL/EL alignment and mandatory FEL enlargement where present.
3. Apply the selected mode's existing algorithm on that grid. AI feature extraction retains its trained input normalization; model and feature meanings do not change.
4. Resample the processed picture to its displayed rectangle when dimensions differ.
5. Compose interface/subtitles at output resolution and encode/quantize/pack the actual output, using the mode's established color domain and order.
6. Present using existing readiness, lifetime and synchronization rules.

This is a logical contract, not six required GPU passes. Fuse operations when doing so preserves the exact required evaluation. If a 4K source already matches the output, scaling is an identity and must not introduce a new pass or intermediate.

Input chroma reconstruction and FEL enlargement are not the final whole-picture upscale. Do not delay those until after the operations that need them. Do not upscale already packed HDMI carrier bytes as an ordinary image.

Preserve PQ/linear/IPT/YCbCr domains per mode. "Common" means common spatial organization, not forcing every mode through RGB or adding color conversions to direct P5 IPT.

## Cleanup boundaries

Replace old routing as each circuit is migrated and qualified. The frozen Git checkpoint is the rollback; no Legacy 1080p toggle or duplicated shipping implementation.

| Existing owner | What changes | What must remain |
| --- | --- | --- |
| CB1 render_picture/render | Replace resolution-specific preparation and backing selection with source-grid processing and a single final fit/pack boundary | Exact reconstruction, mode-specific precision, masks, orientation, crop and final output requirements |
| Master/P5 intermediate handling | Remove unnecessary full-carrier intermediate materialization; make lifetime/consumers explicit | Direct P5 IPT and exact Master scaler/transport; lazy GUI or RGB materialization only when genuinely needed |
| Authored Adaptive allocation/resolve | Remove the dedicated full-1080p transport admission; express useful sample reuse as an output-scaler capability | Current curves, metadata guidance, peak/black protections, anti-pumping and AMD/Intel measured recipes |
| AI prepare/resolve | Separate source processing from output packing; remove accidental policy differences caused solely by source size | Model, feature contract, predictions, identity versus active-expansion distinction and fallback deadlines |
| Libplacebo scaling hooks | Reuse the existing scaler, with fixed filter/precision selected by the mode | Exact tap phases, chroma siting, edges and mathematically necessary ratio/capability guards |
| Tests and patch owners | Replace old implementation-shape assertions with output, geometry, lifetime and ordering checks; delete retired code when unreferenced | Independent pixel/metadata oracles, safety/cancellation coverage and required transport assertions |

Do not remove constants mechanically. A 1920x1080 chroma plane can belong to a 4K P010 picture. The 3840x2160 carrier and bounds checks remain valid. A two-times sampler can legitimately require a two-times ratio. Remove resolution-specific rendering recipes, not protocol facts or exactness guards.

Retain useful Intel/AMD implementation differences behind GPU capability/format requirements. A smaller source must not silently switch its tone curve, PQ treatment or precision merely because it is not 3840x2160. Every retained difference must be attributable to the established mode/format/backend contract.

## Metadata and image guarantees

- Master: zero changed film pixels and metadata compared with the frozen implementation for identical input, geometry, output and backend; independently validate its reference math. No new rounding allowance. If these obligations conflict, stop that change and report the conflict rather than weakening the oracle.
- P5: retain direct IPT for Master and its fixed Standard IPT approximation, without an extra YCbCr/RGB round-trip.
- Other modes: keep existing algorithms, numerical contracts and quality tolerances. No new approximation is authorized by this refactor. Diagnose and expose any required visible/algorithmic change before adopting it.
- 4K picture output and metadata must not regress; retain exact optimizations when their prerequisites still hold.
- L5 geometry is mapped from source coordinates to output once. Preserve established GUI/full-raster handling without putting GUI or subtitles into movie luminance analysis.
- Preserve L1/L3/trims in source-preserving modes. In adaptive/conversion modes, retain their established transformation/measurement policy, source-area normalization and consistency with final filtered output. Do not scan the 4K carrier or black padding as if it were the source picture.
- No master brightness overshoot, crushed blacks or new pumping from reordering.
- Cross-resolution inputs are not expected to have identical pixels: resizing changes the sampling grid. Pixel equality is tested against the same source and output geometry, not between separately encoded 1080p and 4K files.

## Lifetime and presentation

Native intermediates are renderer-owned and reused when compatible; no per-frame allocation or clearing without a demonstrated consumer requirement. Source imports, reconstruction surfaces and final targets retain existing fences until their last actual GPU use. Cancellation, seek, stop and mode changes drain through the existing retirement owner.

No removal of waits merely to improve a timing counter. No additional frame queue. Do not let resolve run the mode algorithm or final scaler twice for the same accepted frame. Retain the current post-resolve ordering and both vendor backends.

## Delivery order

1. Establish the source-grid/final-output boundary through Standard, first non-P5 then P5.
2. Migrate Master Reference, keeping exactness controls and unchanged 4K behavior.
3. Migrate authored Adaptive using the same boundary.
4. Migrate Basic then Expert separately.
5. Check the existing DV-to-HDR10+ RGB/analysis consumer against the same spatial boundary, without a new metadata algorithm. Validate packets, source-area normalization and unsupported-sink fallback offline; do not claim real HDR10+ HDMI qualification without a compatible display.
6. Migrate HDR10 Reference AI then Adaptive AI separately.
7. Remove orphaned branches, resources and tests only after their consumers have moved; verify Master IPT and vanilla exclusions.
8. Build the complete Preview F candidate after all available gates pass, documenting the HDR10+ hardware validation limit.

For each circuit: measure baseline, add failing behavior checks, replace routing, compare pixels/metadata, measure HDMI, remove unsuccessful experiments, review simplification, and repeat qualification after cleanup. Finalize one circuit before starting another.

Do not delete all working 1080p routes first and leave broken stubs. Replacement and deletion form one coherent change per circuit.

## Validation

Reuse current regression suites, resolution_contract, reference scaler/output tests, Master/P5 witnesses, Adaptive lifecycle tests and AI transport tests. Update assertions that pin the old routing; do not weaken pixel/metadata oracles to make the new implementation pass.

Cover:
- native source stage dimensions and exactly one logical spatial fit;
- identity-size 4K without added pass/materialization;
- full-frame 1080p and 1440p, cropped/nonstandard aspect ratio, source L5, edges and orientation;
- P5 direct IPT, P8.1, FEL reconstruction and representative HLG-compatible DV where a fixture exists;
- GUI/subtitles in black bars, pause/play/seek, O-panel cycle, mode changes, home, stop and restart;
- pending/cancel/destroy with in-flight work; import reuse and backend selection;
- both exact and approximate mode contracts, never restoring mutable Fast.

Start with offline GPU witnesses and short hardware tests. Compare paired timing windows on N100 and AMD 3200U at automatic clocks, async On, no GUI for timing, no fallback. Minimize TV use. Confirm identities and pinned addresses before any future hardware session.

Metrics: presented FPS, missed HDMI intervals, render-engine busy ms/picture, occupancy, mean GPU reserve, readiness P01/min and gaps. Do not substitute unavailable Kodi drop/skip counters with zero. Timing with a GUI is a separate workload.

Goal: 1080p should match or beat the equivalent 4K workload, especially 60fps where the corresponding 4K circuit already holds 60fps; zero presentation gaps at 30fps. The 4K60 active Adaptive AI workload is already below 60fps in the baseline, so do not claim the refactor alone guarantees 60fps there. 1440p uses the same path, not a third recipe.

Short windows screen candidates; repeated longer windows qualify stability. Comparisons use the same content and active processing state where possible. Identify differences in decoded source or metadata. No per-pass timing estimate is labelled real-time HDMI headroom.

## Implementation choices left to the builder

Exact internal helper boundaries, pass fusion and scratch ownership may be selected from measurements and existing APIs. Prefer parameterizing existing helpers over adding types/files. Keep dependency versions, driver behavior, model, mode semantics and current user settings unchanged. Maintain source locks and staging receipts at each code checkpoint.

## Approval boundary

This document records the selected architecture and cleanup sequence. Product deletion/refactoring, hardware use and compilation have not started under this design. After user approval, produce the executable implementation plan with Superpowers, then execute the agreed circuit-by-circuit workflow without repeated approval requests for equivalent local changes. No public push, PR or release.

