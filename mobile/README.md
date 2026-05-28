# Videl Mobile (Android)

Flutter port of Videl for Android 10+ (API 29+). Sideload-only — no Play Store constraints.

## Status

MVP scaffold on branch `mobile-android`. Lib/ feature-first skeleton complete; platform code (`android/`) needs `flutter create .` to fill the generated Gradle wrapper + Kotlin Application + resources, then merge the provided overrides below.

## One-time setup

```bash
cd mobile
flutter create .                  # generates android/ ios/ build files
# overwrite the generated files with the ones in this repo:
#   android/app/src/main/AndroidManifest.xml
#   android/app/src/main/kotlin/com/videl/mobile/MainActivity.kt
#   android/app/src/main/python/videl_dl.py
# merge android/app/build.gradle.snippet into the generated build.gradle
# add classpath "com.chaquo.python:gradle:15.0.1" to android/build.gradle

flutter pub get
flutter run                       # connect Android device w/ USB debugging
```

## Layout

```
lib/
  core/
    theme/             dark navy palette mirroring desktop Videl
    native_bridges/    ffmpeg / python / tflite wrappers
    background_service/ sticky foreground service
  models/media_job.dart   universal job schema
  features/
    downloader/        yt-dlp via Chaquopy
    video_tools/       trim, crop, compress, extract audio, transform
    gif_creator/       palette-based GIF encode
    image_suite/       BG eraser, hex palette, image editor
  shared/widgets/      home shell grid
assets/models/         place u2net.tflite here (~40 MB, not in repo)
```

## Required assets

- `assets/models/u2net.tflite` — convert from upstream U2-Net PyTorch weights
  with `tflite-converter` or grab a pre-converted one. NOT committed.

## First-run UX

Because `MANAGE_EXTERNAL_STORAGE` is restricted, the first launch must walk
the user into Settings → Apps → Videl → All-files-access. Wire this via
`permission_handler` (`Permission.manageExternalStorage.request()`).

## Parity with desktop

Same palette (`#060C1A` / `#0A1020` / `#0D1530` bg, `#3B82F6` accent), Inter
typography, card-grid home shell. Tool set is a strict subset — only the
features called out in the mobile MVP brief are exposed.

## Tooling map (desktop → mobile)

| Desktop (`core/`)       | Mobile                            |
|-------------------------|-----------------------------------|
| downloader.py (yt-dlp)  | Chaquopy + `videl_dl.py`          |
| trimmer / chunker / converter / muxer | FFmpegKit one-shot commands |
| bg_eraser.py            | TFLite U2-Net on-device           |
| palette_extractor.py    | Dart K-means on 100×100 downscale |
| image_editor.py         | `pro_image_editor` (crop/rotate/filter/adjust only) |
