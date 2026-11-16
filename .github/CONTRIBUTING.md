# Contributing to LibreELEC × CB1

Join the [LibreELEC forum thread](https://forum.libreelec.tv/thread/30362-x86-64-croquemr-builds-dolby-vision-w-fel-hdr10-and-3d/) to talk about the builds, ask questions, and share your setup or test results.

## Report a bug

1. In Kodi, go to **Settings → System → Logging** and turn on **Enable debug logging**.
2. Reproduce the problem. Note when it happened and what you did just before it.
3. Go to **Settings → LibreELEC → System → Submit Log**. Select **Upload latest Kodi log and configs, and view the short URL**. If Kodi crashed, upload the latest crash log from the same menu too.
4. [Open a GitHub issue](https://github.com/CroqueMr/libreelec-x86-DV/issues/new/choose) and paste the short URL displayed on screen into the **Debug log short URL** field. Include the build version, CPU/GPU, TV or projector, HDMI connections, source format and frame rate, and the selected playback mode. Describe what you expected, what happened, and the exact steps to reproduce it.
5. Turn debug logging off when you're done.

## Request a feature

[Send your suggestion through the form](https://docs.google.com/forms/d/e/1FAIpQLSfCZxNrMoGxVIr-opLA5n26QcMsr47SdQeT1zauwZ8nZCksEA/viewform).

Describe what you are trying to do, how it works today, and what you would like it to do differently. Include the relevant setup, source format or playback mode if it helps explain the idea. An email address is required so we can reply and keep you informed about your suggestion.

## Report a performance problem

Please report stutter, dropped or skipped frames, or slow menus even if you think your hardware is underpowered. A reproducible report helps us determine whether an optimization is possible for your hardware and playback settings.

On lower-powered systems, a few dropped frames while Kodi menus or overlays are open can be expected because they add GPU load. Steady movie playback with subtitles enabled should have zero dropped frames. Please report any drops you see during subtitle playback with the menus closed.

Follow the bug-report steps above. Include the exact CPU/GPU model, source resolution and frame rate, and the playback mode in use. If it happens during video playback, press **O** to open **Player Information** and note the **Drop / Skip** counters and when they increase, such as at startup, after seeking, or during steady playback. Mention whether subtitles or a panel were open, and include a comparison with them closed if it helps reproduce the difference.

Thanks for testing and sharing your feedback!
