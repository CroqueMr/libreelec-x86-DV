# Compact rendering selector implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline.

**Goal:** Restore the previous small bottom-right rendering selector, with safe text insets.
**Architecture:** Keep CGUIDialogSelect selection/navigation and O handling. Load an owned CB1 layout only for the playback selector, like the existing Player information dialog. Ordinary selectors and all skin XML stay unchanged.
**Tech stack:** Kodi native controls, XML and existing panel texture.
**Spec:** User explicitly requests the former compact bottom-right format. Width 660 at the 1920x1080 design coordinate system, right/bottom 40, up to six 50-pixel rows. Reserve a separate padded help area. Video processing, L2 and release identity unchanged.

## Review focus

- Short and long source-specific lists must retain bottom anchoring and native scrolling.
- Help text must stay inside the panel, including HDR10 Expert and unavailable HDR10+.
- Opening another native selector after this one must restore that skin's XML.
- Disabled modes remain unselectable and the O cycle and play/pause keep working.
- No movie renderer, engine source or source metadata changes.

### Task 1: Compact selector and delivery

- [x] Add a failing geometry/ownership regression using the real initializer.
- [x] Restore the prior layout using CB1-owned XML, not copies of skin files; pad heading/help.
- [x] Run integration suite and source/staging checks; inspect the scoped diff independently.
- [ ] Compile a separate complete RC1 artifact; inspect it and install on N100.
- [ ] Capture the actual compact selector, exercise O/ordinary selectors, restore settings, publish nothing.
