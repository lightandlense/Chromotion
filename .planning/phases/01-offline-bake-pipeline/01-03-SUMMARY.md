---
plan: "01-03"
phase: "01-offline-bake-pipeline"
status: complete
completed: 2026-05-12
requirements_satisfied:
  - OFFLINE-08
---

# Summary: Line Art PNG Sequence Export

## What Was Built

- `src/offline/make_lineart_video.py` — exports animation line art as per-frame RGBA PNG sequence
- `src/animations/ram_lineart/` — 121 RGBA PNG frames (frame_0000.png–frame_0120.png)

## Source Video Used

- File: `src/animations/ram_animation_alpha.webm`
- Codec: VP8 with VP8+alpha invisible frame track
- Resolution: 1920x1080
- FPS: 24
- Duration: ~5.04s = 121 frames

## Alpha Extraction Method

VP8+alpha WebM requires explicitly specifying `-vcodec libvpx` in the ffmpeg command. Without this flag, ffmpeg ignores the alpha stream and outputs fully opaque frames (alpha=255 everywhere). With `-vcodec libvpx`, the invisible alpha frame track is decoded and RGBA output is correct.

**Key finding:** Do NOT use `--has-alpha` without `-vcodec libvpx` for VP8 alpha WebMs. Updated `make_lineart_video.py` to use the libvpx decoder when `--has-alpha` is specified.

## Frame Verification (frame_0000.png)

| Metric | Value |
|--------|-------|
| Mode | RGBA |
| Size | 1920x1080 |
| Transparent pixels (alpha=0) | 1,598,781 |
| Opaque pixels (alpha=255) | 467,868 |
| Line art visible (alpha>128) | 471,004 |

Transparency confirmed: ~77% of pixels are transparent (background), ~23% contain line art.

## Colorkey Fallback

`make_lineart_video.py` also supports `--source MP4_PATH` (without `--has-alpha`) using ffmpeg `colorkey=0xffffff:0.15:0.05` to convert white background to transparent. The MP4 source (`ram animation.mp4`) confirmed white corners [255,255,255]. Not used for primary export since the alpha WebM source is cleaner.

## Issues / Deviations

None after fix. Initial export attempt without `-vcodec libvpx` produced fully opaque frames — corrected before committing.

## Self-Check: PASSED

key-files.created:
  - src/offline/make_lineart_video.py
  - src/animations/ram_lineart/
