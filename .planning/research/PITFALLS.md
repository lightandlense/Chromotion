# Pitfalls Research

**Domain:** SAM 2 offline video tracking + Pixi.js sprite rendering + ArUco rectification + public kiosk installation
**Researched:** 2026-05-11
**Confidence:** MEDIUM-HIGH (SAM 2 issues: HIGH via GitHub issues + research papers; Pixi.js memory: HIGH via GitHub issues; ArUco + kiosk: MEDIUM via official docs + community reports)

---

## Critical Pitfalls

### Pitfall 1: SAM 2 VRAM Accumulation Causing OOM During Offline Tracking

**What goes wrong:**
SAM 2's streaming memory buffer grows frame-by-frame and does not automatically release. When tracking 121 frames across 6-9 body parts in sequence, GPU memory accumulates across objects and sessions. Users have reported needing 21-60GB VRAM on longer videos even with `offload_video_to_cpu=True`. A 6-9GB consumer GPU will OOM mid-tracking run with no graceful recovery.

**Why it happens:**
SAM 2 keeps a memory bank of past frame features (conditioned and unconditioned) for its attention mechanism. The bank is not bounded by default. Running multiple `add_new_points` calls for multiple objects in the same session compounds this. Calling `reset_inference_session()` between parts is necessary but not always documented.

**How to avoid:**
- Track one body part per SAM 2 session — call `reset_state()` or reinitialize the predictor completely between parts.
- Set `max_vision_features_cache_size` explicitly to cap memory.
- Use the `sam2-hiera-tiny` or `sam2-hiera-small` checkpoint during development; reserve `sam2-hiera-large` for final bake.
- Run the tracking script with `torch.cuda.empty_cache()` between parts and confirm VRAM is released with `nvidia-smi` before the next part.
- Process parts sequentially, not in a single multi-object session, even though multi-object is supported.

**Warning signs:**
- VRAM usage climbs linearly with frame count in `nvidia-smi` and never drops between parts.
- `torch.cuda.OutOfMemoryError` mid-run with no disk swap fallback.
- Script completes first 2-3 parts then crashes on part 4+.

**Phase to address:** Phase 1 — SAM 2 tracking setup and offline bake script.

---

### Pitfall 2: SAM 2 Windows CUDA Build Failure Blocking All Work

**What goes wrong:**
SAM 2's official installation requires building a custom CUDA extension. On Windows, this fails due to CUDA/Visual Studio version incompatibility, a missing `CUDA_HOME` environment variable, or NVCC not being on PATH. The build error is cryptic and often looks like a compiler error rather than a configuration error. The project stalls before a single mask is produced.

**Why it happens:**
SAM 2 was primarily developed on Linux. The Windows build path requires CUDA Toolkit, Visual Studio Build Tools, and PyTorch CUDA version to all match exactly. The `CUDA_HOME` variable is not set automatically by the CUDA Toolkit installer on all Windows versions.

**How to avoid:**
- Set `SAM2_BUILD_CUDA=0` to skip the CUDA extension build entirely — the extension only affects post-processing, not core tracking quality, so this is safe for this use case.
- Verify Python >= 3.10, PyTorch >= 2.3.1, and CUDA toolkit version match before installing.
- Prefer WSL2 (Ubuntu) for the offline bake pipeline — it eliminates the Windows compiler chain entirely.
- Pin exact versions in a `requirements.txt` for the offline environment to avoid silent upgrades breaking the build.
- Verify with `python -c "import sam2; print(sam2.__version__)"` before writing any tracking code.

**Warning signs:**
- `RuntimeError: The detected CUDA version mismatches the version that was used to compile PyTorch`
- `OSError: CUDA_HOME environment variable is not set`
- `Failed to build the SAM 2 CUDA extension` during `pip install`

**Phase to address:** Phase 1 — environment setup, day one.

---

### Pitfall 3: Rest-Pose Frame Selected with Ambiguous Part Visibility

**What goes wrong:**
The rest-pose frame — the reference frame from which masks are baked and used to slice the visitor scan — is chosen without verifying that all body parts are simultaneously visible, non-occluded, and maximally separated. If the ram's legs overlap each other at rest pose, the corresponding masks will overlap, producing ambiguous slices from the visitor's scan. The 15px dilation makes overlapping masks compound into blobs that cover both adjacent parts.

**Why it happens:**
Animation frame 0 is the natural default choice, but Firefly animations don't guarantee frame 0 is the canonical rest pose. Animators often start and end with an action already in progress. Rest pose is a semantic property, not a frame index.

**How to avoid:**
- Review all 121 frames visually before selecting the rest-pose frame — don't default to frame 0.
- Select a frame where: (a) all six body parts are visible, (b) legs are maximally spread and non-overlapping, (c) the body silhouette most closely matches what a visitor's drawing would depict.
- Store the chosen frame index in `config.json` as `rest_pose_frame` — not hardcoded anywhere.
- Verify that dilated masks do not produce >20% overlap area between adjacent parts by comparing mask bitmaps before committing.

**Warning signs:**
- Dilated mask files for left-leg and right-leg share a large common region.
- Visitor scan slices show color from two different drawing regions blended in a single part.
- The per-part texture PNGs have large transparent areas despite the animal's full body being in frame.

**Phase to address:** Phase 1 — SAM 2 tracking and mask bake step.

---

### Pitfall 4: SAM 2 Click Prompt Placement Causing Mask Leakage into Adjacent Parts

**What goes wrong:**
A click prompt placed near a part boundary causes SAM 2 to assign pixels from an adjacent body part into the current mask. Because adjacent parts share similar color/texture in the animation artwork (clean line art on flat color), SAM 2's region growing bleeds across the boundary. The resulting mask includes half of an adjacent limb, making the baked texture and the slice both incorrect.

**Why it happens:**
SAM 2's prompt is ambiguous when the click is near an interior edge. The model interprets the feature context and may include a larger-than-intended region. Thin limbs (ram legs) are particularly susceptible because the model's low-resolution mask head struggles with narrow structures.

**How to avoid:**
- Place click prompts at the geometric centroid of each part, not near boundaries.
- Use bounding box prompts (not point prompts) for thin limbs — bounding box prompts significantly outperform point prompts for narrow structures.
- Add negative clicks on adjacent parts when boundary leakage appears.
- Visually inspect every mask using the motion_review_tool before baking — do not trust any mask programmatically without a human review pass.
- For parts with consistent leakage, provide prompts on 2-3 frames spread across the video, not just the rest-pose frame.

**Warning signs:**
- A single part's mask covers visibly more pixels than expected when overlaid on the animation frame.
- Two adjacent parts' masks overlap by more than the 15px dilation accounts for.
- Part centroid computed from the mask is clearly not at the visual center of the body part.

**Phase to address:** Phase 1 — SAM 2 tracking, immediately before mask bake.

---

### Pitfall 5: Angle Wrap-Around Discontinuity in motion_data.json

**What goes wrong:**
The animation data for part rotation is stored as raw `atan2` output in radians (range: -π to π). When a limb rotates through the ±π boundary — common in looping animations where a leg swings full-cycle — consecutive frames jump from +3.14 to -3.14. Pixi.js sprite rotation is applied as absolute angle per frame, so the sprite visually snaps 360 degrees backward rather than continuing forward. The animation looks like a random jitter on certain frames.

**Why it happens:**
`atan2` wraps by definition. Storing raw `atan2` output without unwrapping works fine for small motion ranges but breaks for any part with large angular travel across the animation loop. It is easy to miss during testing if the part with the discontinuity moves slowly at the wrap-around frame.

**How to avoid:**
- Apply `numpy.unwrap()` to the full angle sequence for each part before writing `motion_data.json` — this produces a monotonic sequence (e.g., 3.1, 3.2, 3.3 instead of 3.1, -3.1, -3.0).
- Store angles as **unwrapped radians** in `motion_data.json`. Document this convention explicitly in the schema.
- In Pixi.js, compute the delta from the previous frame's angle and apply relative rotation rather than absolute — this makes the renderer immune to any residual wrap-around issues.
- Add a validation step in the bake script that flags any frame-to-frame angle delta > 1.0 radian as a probable wrap-around artifact.

**Warning signs:**
- A sprite snaps suddenly on a specific frame index.
- The frame-to-frame angle delta histogram shows spikes near ±6.28 (2π).
- The motion_review_tool shows a discontinuous angle curve for one part.

**Phase to address:** Phase 1 — motion_data.json schema design and bake script.

---

### Pitfall 6: SAM 2 Mask Drift on Looping Animation

**What goes wrong:**
SAM 2 propagates the mask forward through frames. By frame 80-100 of a 121-frame loop, accumulated tracking errors cause the mask to drift — the boundary drifts outward, the centroid shifts, or the mask fragments into disconnected regions. Since this is a looping animation, the rest-pose frame (used for scan slicing) is computed from a specific frame index, but centroid drift means the sprite position in later frames is offset from what the geometry expects.

**Why it happens:**
SAM 2's memory bank retains past frames but does not detect or correct accumulated drift. Looping animations frequently have the object return to the same pose it started in, but SAM 2 treats it as a new configuration because the memory carries the whole history of drift up to that point.

**How to avoid:**
- After propagating forward to frame 121, propagate backward from the rest-pose frame to frame 0 as well — the backward pass gives independent estimates that can be compared against the forward pass to detect drift.
- Flag frames where the mask area changes by more than 15% relative to the rest-pose mask area — these are likely drift artifacts.
- Implement the outlier interpolation spec'd in PROJECT.md: auto-interpolate flagged frames using the median of the three frames before and after.
- Consider providing a second click prompt at frame 60 (mid-loop) to anchor the tracking — SAM 2 supports prompts on multiple frames in a single session.

**Warning signs:**
- Mask area for a single part changes monotonically across frames (growing or shrinking throughout).
- The bounding box of a part shifts noticeably at frames 90-121 compared to frames 1-30.
- The motion_review_tool shows a smooth curve that doesn't return to its starting value at frame 121 even though the animation loops.

**Phase to address:** Phase 1 — SAM 2 tracking and outlier detection.

---

### Pitfall 7: ArUco Marker Detection Failure Under Kiosk Lighting

**What goes wrong:**
`scan_rectify.py` fails to detect all four ArUco markers on the visitor's drawing because the kiosk lighting produces glare on the scanning surface, insufficient contrast between the marker and the paper, or motion blur from a shaky camera mount. When fewer than four markers are detected, `findHomography` either fails outright or produces an unstable transform that maps the scan to the wrong region.

**Why it happens:**
ArUco detection is sensitive to: (a) lighting uniformity — indoor LEDs produce spectral reflection that wipes out contrast in the binary threshold step, (b) marker physical size — small printed markers at the scan distance may fall below the detection resolution, (c) camera motion blur — even a slight camera shake during capture creates edge blur that breaks the corner detection step.

**How to avoid:**
- Size markers to be at least 80px in the captured image at minimum zoom — test at the actual kiosk distance, not on a desk.
- Use `DICT_4X4_50` or `DICT_5X5_100` dictionaries (larger cells, more robust to blur) rather than higher-density dictionaries.
- Add a brightness/contrast normalization step before ArUco detection: `cv2.equalizeHist` or CLAHE on the grayscale channel.
- Validate all four markers detected before computing homography — if fewer than 4, return a structured error code (not a crash) and display a "please rescan" prompt to the visitor.
- Keep the ORB alignment fallback in `scan_rectify.py` as spec'd — it handles the case where one marker is obscured by the visitor's drawing extending over the corner.
- After homography is computed, validate it: `np.linalg.det(H)` must be > 0 and the projected corners must fall within the expected bounding box.

**Warning signs:**
- Detection works in testing under bright even light but fails in the venue.
- Fewer than 4 markers detected on >10% of scans in a batch test.
- The rectified scan is skewed, upside-down, or clipped — indicates a degenerate homography was accepted without validation.

**Phase to address:** Phase 1 — scan_rectify.py implementation and venue lighting test.

---

### Pitfall 8: Pixi.js Texture Memory Leak Across Visitor Sessions

**What goes wrong:**
Each visitor triggers a scan-slice-load cycle that creates new `Texture` objects from the per-part PNG files. When the display resets for the next visitor, the old textures are not explicitly destroyed. Over 50+ visitor sessions, VRAM and system RAM fill up, the browser slows, and eventually Chrome crashes or the WebGL context is lost — effectively killing the installation.

**Why it happens:**
Pixi.js does not automatically garbage-collect GPU textures when sprites are removed from the stage. The `Texture` object holds a WebGL resource reference that persists until `texture.destroy(true)` is called explicitly. The `textureGCMaxIdle` setting (default: 2 hours) is far too long for a high-traffic kiosk where sessions cycle every 2-3 minutes.

**How to avoid:**
- On every session reset, call `texture.destroy(true)` on all per-part visitor textures — the `true` argument destroys the underlying GPU resource, not just the Pixi object.
- Create a `SessionTextureManager` that registers all dynamically loaded textures and exposes a `cleanup()` method — call it as part of the session-end event.
- Do not use `Texture.from()` (which caches globally) for visitor textures — use `new Texture(new BaseTexture(url))` and hold the reference yourself.
- Set `textureGCMaxIdle` to 30 seconds for the kiosk renderer instance.
- Stagger texture destruction if multiple textures are destroyed at once — destroy 1-2 per frame to avoid a single-frame hitch.
- Run a 4-hour soak test before public opening: cycle through 100 simulated sessions and monitor Chrome's memory in DevTools.

**Warning signs:**
- Chrome's task manager shows steadily increasing memory for the tab over 30+ minutes.
- Frame rate drops from 60fps to 40fps after 20+ visitor cycles.
- `webglcontextlost` event fires — this is the terminal failure signal.
- DevTools Memory heap grows monotonically between sessions.

**Phase to address:** Phase 2 — Pixi.js renderer implementation; verified in Phase 3 soak testing.

---

### Pitfall 9: WebGL Context Loss with No Recovery in Kiosk Mode

**What goes wrong:**
Chrome loses the WebGL context — typically because the GPU driver resets due to a too-long GPU operation, Windows TDR (Timeout Detection and Recovery), or too many simultaneous WebGL contexts on the machine. When this happens with no recovery handler, the renderer silently stops drawing. The installation displays a frozen frame or black canvas and cannot self-recover without a page reload.

**Why it happens:**
WebGL context loss is a browser-level event. By default, when it is lost, it is never restored. The `webglcontextlost` event fires but nothing listens to it. Integrated Intel GPUs on Windows are specifically documented as producing context loss under memory pressure.

**How to avoid:**
- Add a `webglcontextlost` event listener on the canvas element that calls `event.preventDefault()` to signal intent to recover.
- Add a `webglcontextrestored` event listener that reinitializes the Pixi app, reloads static textures (line art overlay), and returns to the idle/attract state.
- If recovery fails after 3 attempts, trigger a full page reload via `window.location.reload()` — this is acceptable kiosk behavior.
- Monitor context loss in production with a simple counter logged to `localStorage` — if it exceeds 1 per hour, investigate GPU driver or memory pressure.
- Use a Pixi.js `ticker` health check: if the ticker hasn't fired in 2 seconds, assume context loss and attempt recovery.

**Warning signs:**
- Canvas goes black or freezes mid-animation.
- The `webglcontextlost` event fires in the browser console.
- GPU memory usage in Task Manager is near maximum.

**Phase to address:** Phase 2 — Pixi.js renderer, kiosk harness setup.

---

### Pitfall 10: Video Texture Frame Sync Mismatch with Sprite Transform Frames

**What goes wrong:**
The spec calls for a WebM video as the line art overlay, with Pixi.js sprites driven by `motion_data.json` frame indices. The video plays at 24fps under browser-controlled timing, while the Pixi.js ticker runs at 60fps. These clocks drift: after 5 seconds, the video is at frame 120 but the sprite transform is at frame 124 or 116 depending on the drift direction. The line art and the colored body parts are visibly misaligned.

**Why it happens:**
`HTMLVideoElement` uses the browser's media pipeline clock. Pixi.js `Ticker` uses `requestAnimationFrame`. They are not synchronized and will diverge. The spec notes a PNG sequence fallback for exactly this reason, but if the WebM path is used without sync logic, the mismatch appears immediately.

**How to avoid:**
- Do not use elapsed time to index `motion_data.json` — use the video's `currentTime` property converted to a frame index: `frameIdx = Math.round(video.currentTime * fps)`.
- Drive ALL sprite transforms from the video's `currentTime`, not from an independent Pixi.js ticker-based counter.
- Cap `frameIdx` to `[0, totalFrames - 1]` to handle video seek/loop edge cases.
- Implement the PNG sequence fallback as the default path for Phase 1 — it is frame-perfect and eliminates the sync problem entirely. Introduce WebM only after the PNG path is validated.

**Warning signs:**
- Line art horns appear 2-3 pixels offset from the colored head sprite.
- The offset grows over time within a single playback cycle and resets at loop.
- Switching from WebM to PNG sequence eliminates the artifact.

**Phase to address:** Phase 1 — Pixi.js renderer, frame indexing implementation.

---

### Pitfall 11: CORS Blocking Texture Loads in Local Kiosk Context

**What goes wrong:**
`part_renderer.js` attempts to load per-part PNG textures using relative file paths. When the kiosk page is opened via `file://` protocol (directly opening `index.html`), Chrome blocks all texture loads with a CORS error. No sprites appear. The kiosk appears to work during development (via localhost) but silently fails when deployed to the venue machine via file drop.

**Why it happens:**
Chrome's security model treats `file://` origins as cross-origin for XHR and Fetch. Pixi.js uses Fetch to load textures, which inherits this restriction. The error is often not visible unless DevTools is open.

**How to avoid:**
- Always serve the kiosk from a local web server — even a simple `python -m http.server 8080` launched at startup resolves this.
- Add a `kiosk-start.bat` (Windows) that starts the server and launches Chrome in kiosk mode pointing to `localhost:8080` — never open `index.html` directly.
- Test explicitly by deploying the full file set to a clean machine and verifying via the startup script, not by opening the HTML file manually.
- Do not use `--allow-file-access-from-files` Chrome flag as a workaround — it introduces a security surface and is not reliable across Chrome versions.

**Warning signs:**
- `CORS error: Cross origin requests are only supported for protocol schemes: http, data, chrome, etc.` in the console.
- All sprites are invisible but no JavaScript error is thrown.
- Works on developer machine (localhost) but not on venue machine.

**Phase to address:** Phase 1 — deployment setup, kiosk launch script.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode rest-pose frame index in script | Saves one config lookup | Breaking change when animation is re-exported; forces re-bake of all assets | Never — always use `config.json` |
| Store raw `atan2` angles without unwrapping | Simpler bake script | Snap artifacts at ±π for any part with large angular travel | Never |
| Multi-object SAM 2 session for all parts at once | Fewer session init calls | Near-certain OOM on consumer GPU for 121-frame video with 6+ objects | Never |
| Load visitor textures via `Texture.from()` (global cache) | One-liner convenience | Textures never freed; guaranteed memory leak over session count | Never |
| File:// protocol for kiosk deployment | No server to maintain | CORS blocks all texture loads silently | Never |
| Skip ArUco homography validation (det check) | Fewer lines of code | Degenerate homography produces garbage rectification with no error | Never |
| Use `sam2-hiera-large` checkpoint during all development | Best mask quality | 4-8x longer tracking time, higher OOM risk during iteration | Only for final bake |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| SAM 2 + Windows CUDA | Assume the pip install worked because no error was shown | Run `python -c "from sam2.build_sam import build_sam2_video_predictor; print('ok')"` explicitly |
| SAM 2 checkpoint loading | Download checkpoint without verifying SHA256 | Always verify checksum after download; a partial download produces silent wrong-mask results |
| ArUco + OpenCV | Use default `DICT_6X6_250` dictionary | Use `DICT_4X4_50` — lower density means more robust detection under blur and low contrast |
| Pixi.js v7 + dynamic textures | Use `Texture.from(url)` expecting cache invalidation per session | `Texture.from()` caches by URL; append `?v=<session_id>` to bust the cache or manage textures manually |
| Video texture + sprite sync | Use `Date.now()` delta for frame indexing | Use `video.currentTime * fps` as the authoritative frame index |
| SAM 2 + looping video | Prompt only on frame 0 and propagate forward | Propagate both directions from rest-pose frame; add a mid-loop anchor prompt |
| Python scan pipeline + kiosk runtime | Call subprocess from JavaScript | Pre-bake all motion data offline; runtime Python call would violate the 3-second budget and add process management complexity |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| SAM 2 large checkpoint for every development iteration | 20+ minute bake time per part change | Use `sam2-hiera-tiny` during development; swap to large only for final bake | First iteration where you change rest-pose frame |
| Loading per-part PNGs individually at runtime | 200-400ms texture load time per part, totaling 1.2-2.4s of 3s budget | Pre-load all static creature textures at app start; only visitor textures load at session time | When 6+ parts load sequentially on first visitor |
| Running ArUco detection on full-resolution camera frame | Detection call takes 300-500ms on a 4K frame | Downsample capture to 1280x720 for detection; use that resolution for homography computation | Any camera resolution above 1080p |
| Destroying all visitor textures in a single frame | 100ms+ frame hitch as GPU deallocates | Stagger destruction: 1-2 textures per frame over 3-4 frames | After >4 simultaneously destroyed textures |
| Motion data JSON with full float precision (15 decimal places) | Oversized JSON, slow parse | Round to 4 decimal places — sub-pixel accuracy is meaningless for sprite transforms | Never a correctness issue; a startup latency issue at scale |

---

## "Looks Done But Isn't" Checklist

- [ ] **SAM 2 tracking:** Masks visually reviewed in motion_review_tool for ALL 121 frames, not just the first 10 and last 10 — drift typically appears in the middle.
- [ ] **Rest-pose mask bake:** Dilated mask PNGs rendered with the actual dilation radius applied, not just the binary mask — verify visually by overlaying on the animation frame.
- [ ] **motion_data.json angles:** Unwrapped angle sequence validated by plotting — a flat or smooth curve with no sudden ±6.28 jumps, not just "no Python errors."
- [ ] **ArUco rectification:** Tested with a physical printout under kiosk lighting conditions, not just a screen-displayed marker under desk lighting.
- [ ] **3-second budget:** Measured end-to-end on the target venue hardware (not the developer's machine) with a cold browser cache and a real scan image.
- [ ] **Session cleanup:** Memory profile shows stable RAM/VRAM after 20+ simulated sessions in Chrome DevTools, not just after one session reset.
- [ ] **Context loss recovery:** `webglcontextlost` event handler tested by manually triggering context loss (available via WebGL extension `WEBGL_lose_context`).
- [ ] **CORS / server launch:** Kiosk tested by deploying to a clean Windows machine via the startup script — not opened via `file://` or from a developer machine.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| VRAM OOM mid-bake | LOW | Add `reset_state()` between parts; rerun from last successful part using checkpoint files |
| Windows CUDA build failure | LOW | Set `SAM2_BUILD_CUDA=0` and reinstall; or switch to WSL2 |
| Wrong rest-pose frame chosen | MEDIUM | Re-select frame, re-run SAM 2 tracking, re-bake masks; ~2 hours per creature |
| Mask drift discovered late | MEDIUM | Add anchor prompt at drift frame, re-propagate from that frame forward |
| Texture memory leak found in production | HIGH | Add `destroy(true)` calls immediately; deploy hotfix; run soak test before reopening |
| WebGL context loss in production | LOW | Deploy context loss recovery handler; if frequent, add page-reload fallback |
| ArUco detection failing at venue | MEDIUM | Increase marker size on printed sheet; add CLAHE normalization; test ORB fallback |
| Video sync drift | LOW | Switch to PNG sequence path (already in spec as fallback) |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| SAM 2 VRAM accumulation OOM | Phase 1 — tracking script architecture | `nvidia-smi` shows stable VRAM across 6-part bake run |
| SAM 2 Windows CUDA build failure | Phase 1 — environment setup day one | `python -c "from sam2.build_sam import build_sam2_video_predictor"` succeeds |
| Rest-pose frame with overlapping parts | Phase 1 — rest-pose frame selection | Dilated mask overlap area < 20% between adjacent parts |
| Click prompt causing mask leakage | Phase 1 — tracking and mask review | All masks pass visual inspection in motion_review_tool |
| Angle wrap-around discontinuity | Phase 1 — motion_data.json bake script | Frame-to-frame angle delta histogram shows no spikes > 1.0 rad |
| SAM 2 mask drift on looping animation | Phase 1 — tracking and outlier detection | Auto-flagged outlier frames < 5% of total frames across all parts |
| ArUco detection failure | Phase 1 — scan_rectify.py + venue test | Detection rate > 99% on 50-scan batch test under venue lighting |
| Pixi.js texture memory leak | Phase 2 — renderer implementation | Stable heap after 50 simulated session cycles in DevTools |
| WebGL context loss, no recovery | Phase 2 — kiosk harness | Context loss recovery tested via WEBGL_lose_context extension |
| Video texture frame sync mismatch | Phase 1 — frame indexing | PNG sequence path default; no visible misalignment at frame 120 |
| CORS blocking texture loads | Phase 1 — kiosk launch script | Tested on clean venue machine via startup script, not file:// |

---

## Sources

- [SAM 2 VRAM OOM — HuggingFace Discussion](https://discuss.huggingface.co/t/sam2-video-streaming-vram-usage-keeps-increasing-until-oom/168526)
- [SAM 2 GPU Memory Not Released — GitHub Issue #258](https://github.com/facebookresearch/segment-anything-2/issues/258)
- [SAM 2 VRAM Benchmarks — GitHub Issue #118](https://github.com/facebookresearch/sam2/issues/118)
- [SAM 2 Windows CUDA Install Tutorial — GitHub Issue #80](https://github.com/facebookresearch/segment-anything-2/issues/80)
- [SAM 2 CUDA_HOME Not Set — GitHub Issue #41](https://github.com/facebookresearch/segment-anything-2/issues/41)
- [SAM 2 Installation Guide](https://github.com/facebookresearch/sam2/blob/main/INSTALL.md)
- [SAM2Long: Long Video Mask Drift Research — ICCV 2025](https://arxiv.org/html/2410.16268v3)
- [SAM 2 Video Segmentation Tutorial — Roboflow](https://blog.roboflow.com/sam-2-video-segmentation/)
- [SAM 2 Small Object Failure — Ultralytics Docs](https://docs.ultralytics.com/models/sam-2)
- [ArUco Detection Tutorial — OpenCV Official](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html)
- [ArUco Low Light Performance — OpenCV Issue #26686](https://github.com/opencv/opencv/issues/26686)
- [Pixi.js Garbage Collection — Official Docs](https://pixijs.com/8.x/guides/concepts/garbage-collection)
- [Pixi.js Texture Memory Leak — GitHub Issue #2220](https://github.com/pixijs/pixijs/issues/2220)
- [Pixi.js WebGL Context Loss — GitHub Issue #6494](https://github.com/pixijs/pixijs/issues/6494)
- [Pixi.js Video Texture Stutter — GitHub Issue #7624](https://github.com/pixijs/pixijs/issues/7624)
- [Pixi.js CORS Local File — GitHub Issue #7552](https://github.com/pixijs/pixijs/issues/7552)
- [WebGL Handling Context Lost — Khronos Official](https://www.khronos.org/webgl/wiki/HandlingContextLost)
- [Chrome Kiosk OOM After 8+ Hours — Grafana Issue #50820](https://github.com/grafana/grafana/issues/50820)
- [Angle Discontinuity in Animation — numpy.unwrap docs](https://numpy.org/doc/2.1/reference/generated/numpy.unwrap.html)
- [Rotation Discontinuity in Neural Pipelines — Orange Duck](https://theorangeduck.com/page/unrolling-rotations)

---
*Pitfalls research for: SAM 2 + Pixi.js offline-to-runtime color transfer pipeline, Color Animals Interactive kiosk*
*Researched: 2026-05-11*
