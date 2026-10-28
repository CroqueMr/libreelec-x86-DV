# RC1 final native selection

User request: remove Adaptive rev B, retain the existing Adaptive, correct the
rendering selector through Kodi-native UI, show a real screenshot and compile
the complete RC1 image. No publication requested.

The current selector injects an Estuary layout with a transparent panel and
fixed margins/help height. Text can meet the visible edge and overrun the help
area. Increasing those constants would preserve the skin-specific workaround.

Use the existing CGUIDialogSelect detailed-list API unchanged. The active skin
owns its title, margins, item rows, scrolling, background and descriptions.
Remove our Estuary selector XML and runtime geometry overrides, not the skin's
native files. Preserve source-specific choices, blocking reasons, selection
validation, playback controls and the O information/selection/video cycle.

Remove rev B runtime, API fields, choices and tests. Preserve the accepted
Adaptive and all other movie algorithms, including the later SDR recovery fixes.
Normalize a saved private rev B choice to the retained Adaptive on upgrade.

Build DV-R1.0.0-RC1, GitHub identity R1.0.0-RC1. Keep previous private image
artifacts recoverable. No new renderer, scaler, skin source or dependency.

Validation: failing native-layout/removal tests, full engine/integration suites,
patch replay and source receipts, complete image inspection, actual selector
capture with Expert help and video behind it. Do not claim new performance or
zero-drop certification from a UI capture.
