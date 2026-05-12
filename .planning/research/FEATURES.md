# Feature Research

**Domain:** Interactive art installation — visitor-coloring + live animated projection
**Researched:** 2026-05-11
**Confidence:** HIGH (derived from full spec suite: track2-sam2-hybrid_spec, kiosk-ui_spec, scan-pipeline_spec, scene-manager_spec, creature-behaviors_spec, color-extraction_spec, and existing implementation plan)

---

## Feature Landscape

### Table Stakes (Visitors and Operators Expect These)

Features that are not optional. Missing any one of these = the installation is broken or embarrassing.

#### Visitor Experience

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Scan produces visible, recognizable result on-screen | The entire value proposition — without it, the kiosk is just a scanner | HIGH | End-to-end: ArUco rectify → slice → Pixi renderer loop |
| Visitor's crayon colors appear on the creature (not a generic palette) | If colors are wrong or generic, visitors feel the scan did nothing | HIGH | 1:1 color fidelity is a hard requirement; Track 2 construction guarantees this |
| Creature animation runs correctly after scan | Visitor sees their creature move, not a static image | MEDIUM | Pixi renderer + motion_data.json; existing Firefly animation is the source |
| Sub-3-second scan-to-display time | Museum/gallery context — visitors lose interest fast; long waits feel broken | HIGH | Drives offline-heavy architecture: no SAM 2 at runtime |
| Graceful failure on bad scan (no crash, user gets clear retry prompt) | Webcam angle, lighting, or missing ArUco markers will happen constantly | MEDIUM | ArUco missing → "hold closer", dim scan → "try again", all detected before processing |
| Uncolored regions render white (not as artifacts or gaps) | Partial coloring is normal visitor behavior; artifacts destroy the art | LOW | Handled by scan_slice alpha channel — all-white texture is valid output |
| Line art renders on top of colored regions | Without this, dark crayon colors obliterate the outline and the creature reads as a blob | MEDIUM | Transparent WebM (or PNG sequence fallback) composited as topmost Pixi layer |

#### Offline Pipeline (Operator/Developer)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| SAM 2 tracks all body parts for all animation frames | Entire rendering approach depends on baked motion data; wrong tracking = wrong animation | HIGH | sam2_tracker.py + build_motion_data.py; one-time run per creature |
| Rest-pose masks baked with 15px dilation | Without dilation, crayon strokes at region edges render in the wrong part | LOW | Hardcoded in build_motion_data.py |
| Outlier frame auto-interpolation | SAM 2 will produce jitter frames; without this, the animation glitches visibly | MEDIUM | outlier_fixer.py; centroid-jump threshold 50px |
| motion_data.json and rest_pose_masks are reusable across all visitor scans | Operator cannot re-run SAM 2 between visitors — baked data must be stable | LOW | By construction: offline pipeline runs once, runtime uses baked files |
| ArUco homography rectification | Webcam angle is never perfectly orthogonal; without rectification, scan colors land in wrong parts | MEDIUM | aruco_rectify.py; ORB alignment as fallback |

#### Authoring Tool (One-Time Per Creature)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Click-prompt tool to define part centroids | SAM 2 needs seed points for each body part; authoring these must be interactive, not guessed | MEDIUM | click_prompt_tool.py — Tkinter UI, click → name → saves parts_config.json |
| parts_config.json z_order control | Limbs behind/in-front of body must be correct or the creature looks anatomically wrong | LOW | Manual edit after click-prompt tool run |

---

### Differentiators (What Makes This Installation Memorable)

Features visitors will actively notice and talk about.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Exact stroke texture fidelity — crayon hatching, pressure variation, out-of-line marks all appear on the animated creature | This is what separates this from "generic color-by-region" kiosks (e.g. Quiver AR) — the visitor's actual artistic marks are visible in motion | HIGH | Core insight of Track 2: scan IS the texture; no diffusion or sampling |
| Dark colors render faithfully (black crayon, navy, deep purple) | Competing approaches (brightness-threshold compositing) treat dark colors as line art and erase them | MEDIUM | Line art composited on top, no brightness gate on scan texture; dark colors survive |
| Visitor colors outside the lines and it still looks intentional | Out-of-line strokes appear on the part they're inside, not as errors | LOW | 15px dilation captures boundary spillover; z-order resolves overlaps |
| Creature joins a persistent shared scene with other visitors' creatures | Social/collective dimension — visitors look for their creature among others on the wall | MEDIUM | Scene manager supports up to 30 concurrent creatures; depth layering creates parallax |
| Seamless looping animation with idle + action behavior states | Museum context: animation must loop indefinitely without jarring cuts | MEDIUM | Firefly animations are pre-generated per creature; action triggers randomized every 8-15s |
| motion_review_tool manual brush correction for bad SAM 2 frames | Allows art-quality control over the baked motion data without re-running full pipeline | MEDIUM | Tkinter UI; flagged frames (tracking_quality < 0.6 for 3+ consecutive) highlighted; deferred to post-Phase-1 if auto-interpolation covers it |
| Render mode escalation path (rigid → split_joints → mesh_deform) | Per-creature quality tuning without re-engineering the pipeline; flying creatures (butterfly, jellyfish) need mesh_deform for wing flex | HIGH | parts_config.json render_mode field; only rigid needed for Phase 1 ram |

---

### Anti-Features (Deliberately NOT Building in Phase 1)

Features that look useful but are complexity traps at this stage.

| Feature | Why Requested | Why Problematic | What to Do Instead |
|---------|---------------|-----------------|-------------------|
| Real-time SAM 2 tracking at scan time | "Why bake offline? Track on the fly for fresher data" | Blows the 3-second runtime budget; SAM 2 on video needs frames to propagate across, which is inherently offline | Pre-bake motion_data.json offline; it covers all 121 frames completely |
| Optical flow warping at runtime (previous Track 1 approach) | Sounds like a flexible "bring your own animation" approach | Confirmed failed: DIS flow bleeds colors at boundaries, white gaps at extended poses, gray artifacts; the root cause is unfixable — flat scan cannot bridge real pose differences | Texture-per-part slicing approach; no warping ever |
| Per-visitor personalized AI animation generation (Option A in creature-behaviors_spec) | "Each visitor gets a unique animation based on their colors" | 1-2 min generation time per visitor; destroys the kiosk flow; unpredictable AI output quality; needs GPU cloud dependency | Use Option B: pre-baked animation, apply visitor colors as texture at runtime |
| Color sampling / median extraction for region tinting (old color-extraction_spec approach) | Simpler to implement — no slicing needed | Loses all stroke texture and color variation; visitor's art becomes a flat tint; fails the core value proposition | Per-pixel scan texture slicing (Track 2) |
| split_joints and mesh_deform rendering modes in Phase 1 | Better visual quality for limb bending | Unknown engineering cost; quality gate not yet reached; rigid mode is correct approach to validate first | Gate on Task 17 Russell approval; escalate only if rigid looks bad |
| Creature-ID QR codes (vs printed ArUco numbers) | More robust creature recognition at scale | Requires pyzbar/opencv QR; more complex template printing; Phase 1 is ram-only so creature ID detection is irrelevant | Keep printed number + pytesseract; upgrade path documented in scan-pipeline_spec |
| Projector output formatting | Final installation needs precise projector calibration | Hardware not yet selected; pre-commissioning work that blocks no software validation | Defer until hardware is locked; browser canvas output is sufficient for Phase 1 |
| Kiosk hardware integration beyond webcam capture | Full production kiosk enclosure | Hardware not locked; any code against specific hardware is throw-away | Use webcam on dev machine; hardware integration is post-gate work |
| Multi-creature scanning in one session | "What if a family colors three creatures at once?" | State machine complexity; scan-to-creature mapping becomes ambiguous; creature-limit management harder | Single scan per session; IDLE → SCAN → PREVIEW → SUBMIT → IDLE is the validated flow |
| Undo / re-color after submission | Natural visitor request | Once the creature is in the scene it's part of the shared installation art; undo breaks the collective experience | "Try again" exists in PREVIEW state before submission — that's sufficient |

---

## Feature Dependencies

```
ArUco corner detection
    └──required by──> Homography rectification
                          └──required by──> Scan slicing (scan_slice.py)
                                               └──required by──> Per-part texture upload to Pixi

SAM 2 offline tracking (sam2_tracker.py)
    └──produces──> motion_data.json + rest_pose_masks/
                      └──required by──> Pixi.js part renderer (track2_renderer.js)
                      └──required by──> Scan slicing (masks define where to slice)

Click-prompt authoring tool (click_prompt_tool.py)
    └──produces──> parts_config.json
                      └──required by──> SAM 2 offline tracking (click prompts are the seed)

Transparent line-art video (make_lineart_video.py)
    └──required by──> Pixi.js part renderer (composited as topmost layer)

Outlier interpolation (outlier_fixer.py)
    └──enhances──> motion_data.json quality
    └──required before──> Pixi renderer (bad outlier frames = visible glitch in animation)

motion_review_tool.py [DEFERRED]
    └──enhances──> motion_data.json (manual correction of SAM 2 drift blocks)
    └──depends on──> motion_data.json existing (repair tool, not a producer)

render_mode: split_joints / mesh_deform [DEFERRED]
    └──depends on──> render_mode: rigid passing visual quality gate
    └──enhances──> limb bending quality for complex creatures
```

### Dependency Notes

- **ArUco detection must succeed for any scan to proceed:** All runtime processing is gated on finding 4 markers. Missing markers is the most common failure mode in a gallery setting (bad lighting, paper angle) and must produce a clear retry prompt.
- **parts_config.json must be authored before offline pipeline runs:** click_prompt_tool.py is the only input to SAM 2 beyond the animation video. Badly-placed click prompts (wrong region, body contamination) produce bad masks with no warning until visual review.
- **motion_data.json and rest_pose_masks must both be present for the runtime to start:** The Pixi renderer hard-errors if either is missing. A "creature unavailable" placeholder handles this edge case.
- **Offline pipeline runs per-creature, once:** The output is stable and reused for every visitor scan. Re-running is only needed if the animation asset changes or quality is unsatisfactory after Task 17 review.
- **motion_review_tool enhances but is not blocking for Phase 1:** Auto-interpolation (outlier_fixer.py) handles single-frame glitches. The review tool is needed only if SAM 2 drifts to the wrong object for multiple consecutive frames — which may not happen with the ram's relatively simple walk cycle.

---

## MVP Definition

### Launch With (Phase 1 — Ram Validation)

Minimum feature set to validate the Track 2 approach and reach the quality gate.

- [ ] click_prompt_tool.py — author parts_config.json interactively
- [ ] sam2_tracker.py + build_motion_data.py — bake motion_data.json and rest_pose_masks for ram
- [ ] outlier_fixer.py — auto-interpolate single-frame centroid jumps
- [ ] make_lineart_video.py — extract transparent line-art WebM from Firefly animation
- [ ] aruco_rectify.py — perspective-correct visitor scan to animation-frame resolution
- [ ] scan_slice.py — cut rectified scan into per-part RGBA textures using rest-pose masks
- [ ] track2_renderer.js — Pixi.js v7 sprite renderer with per-frame transforms + line-art composite
- [ ] process_scan.py runtime CLI — end-to-end scan → rectify → slice in one command
- [ ] Visual test: flat-color reference scan, real crayon scan, dark-color edge case, sparse scan
- [ ] Performance gate: full runtime path completes under 3 seconds
- [ ] Russell visual approval gate (Task 17) comparing Track 2 vs rigid_color_transfer output

### Add After Validation (Post-Gate, Pre-Scale)

- [ ] motion_review_tool.py — add if auto-interpolation misses multi-frame SAM 2 drift blocks
- [ ] split_joints render mode — add if rigid shows unacceptable knee-bending for any quadruped
- [ ] PNG sequence fallback for line-art — add if WebM video decode proves unreliable in browser

### Future Consideration (19-Creature Scale)

- [ ] mesh_deform render mode — needed for wing/fin flex (butterfly, jellyfish, manta ray)
- [ ] parts_config.json authoring for remaining 18 creatures — gate on Phase 1 approval
- [ ] Kiosk hardware integration — projector output formatting, enclosure webcam, physical button
- [ ] Creature ID QR code upgrade — when scanning 19 creature types in parallel
- [ ] Multiplayer scene: up to 30 concurrent visitor creatures in shared projected space

---

## Feature Prioritization Matrix

| Feature | Visitor Value | Implementation Cost | Priority |
|---------|--------------|---------------------|----------|
| ArUco rectification + scan slicing | HIGH — wrong colors = failure | MEDIUM | P1 |
| Pixi.js part renderer (rigid mode) | HIGH — the visible output | MEDIUM | P1 |
| Transparent line-art composite | HIGH — dark colors would otherwise disappear | MEDIUM | P1 |
| SAM 2 offline tracking + motion_data.json | HIGH — foundation for all rendering | HIGH | P1 |
| Click-prompt authoring tool | HIGH — required to run SAM 2 at all | MEDIUM | P1 |
| Outlier auto-interpolation | HIGH — prevents visible animation glitches | LOW | P1 |
| Sub-3-second runtime gate | HIGH — gallery UX requirement | LOW (architecture decision already made) | P1 |
| Graceful scan failure prompts | MEDIUM — visitors recover without staff | LOW | P1 |
| motion_review_tool manual correction | MEDIUM — quality safety net | MEDIUM | P2 |
| PNG sequence line-art fallback | LOW — insurance against WebM issues | LOW | P2 |
| split_joints render mode | MEDIUM — better knee bending | MEDIUM | P2 (post-gate) |
| mesh_deform render mode | HIGH for flying creatures | HIGH | P3 (19-creature scale) |
| Projector output formatting | HIGH for production | MEDIUM | P3 (post-hardware) |

---

## Complexity Traps: SAM 2 + Video Color Transfer Specific

These are failure modes that look like feature requests but are actually technical sinkholes.

### Trap 1: Trying to Fix Warping Artifacts Instead of Eliminating Warping

**Symptom:** Each artifact fix (gap fill, silhouette composite, brightness threshold, IK-ring removal) creates a new artifact. You end up with a pipeline of compensating hacks.
**Root cause:** Optical flow on sparse line art is fundamentally unreliable. No amount of post-processing recovers from this.
**Resolution:** Track 2 eliminates warping entirely. The scan never moves. SAM 2 tracks the animation geometry; the scan texture is applied per-part statically.

### Trap 2: Runtime SAM 2 Inference

**Symptom:** "Why bake offline? Just run SAM 2 on the scan at runtime."
**Why it fails:** SAM 2 is a video model — it propagates masks across frames. It cannot process a single-frame scan in isolation to produce all 121 frames of motion data in under 3 seconds. On an RTX 4090, processing a 121-frame video with 8 parts takes 1-5 minutes.
**Resolution:** Architecture is offline-heavy by design. Runtime does only two things: ArUco rectify + alpha-channel slice.

### Trap 3: Click Prompt Placement Errors Silently Producing Bad Masks

**Symptom:** SAM 2 segments body/neck together because the click for "neck" was too close to the body centroid. The resulting motion_data.json is wrong and only fails at visual review.
**Prevention:** Author click prompts on a high-resolution frame 0 reference image. Include visual verification step: inspect rest_pose_masks/*.png alpha channels before baking motion_data.json. Re-click if any mask includes pixels from a neighboring part.

### Trap 4: Overlapping Mask Regions Without z_order Control

**Symptom:** 15px dilation causes adjacent masks to overlap at joints. Without z_order, parts render in insertion order and near-side limbs appear behind the body.
**Prevention:** parts_config.json z_order is required and must be authored manually after click-prompt authoring. The pipeline does not infer z_order.

### Trap 5: Brightness Threshold on Scan Texture

**Symptom:** "Dark crayon looks like line art — let's filter pixels below brightness 30 out of the scan." This erases dark-colored regions from the output.
**Resolution:** Never apply a brightness gate to the scan texture. The line-art overlay strategy eliminates the need: render colored sprites first, composite line-art WebM on top at full opacity. Dark colors survive because they live in the sprite layer, not the line layer.

### Trap 6: SAM 2 Drift to Background on Long Animations

**Symptom:** After frame 60 of 121, SAM 2 starts tracking a background element instead of the leg. tracking_quality drops below 0.6 for a sustained block.
**Detection:** outlier_fixer.py flags single-frame centroid jumps (>50px). Sustained drift (>3 consecutive frames with tracking_quality < 0.6) requires motion_review_tool.
**Prevention for Phase 1:** The ram animation is a simple walk cycle against a plain white background (Firefly-generated). Drift risk is low. Monitor during Task 9 (run offline pipeline) and add motion_review_tool only if needed.

---

## Phase-Specific Feature Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| SAM 2 install (Task 1) | pip installing SAM 2 may silently downgrade torch+cu128 to CPU build | Dry-run check first; see feedback_pip_torch_conflicts.md |
| Click-prompt authoring (Task 2-3) | Clicking "neck" too close to body → SAM 2 tracks body+neck as one part | Visual verification of frame 0 mask before full pipeline run |
| SAM 2 tracking (Task 6-9) | CUDA OOM on RTX 4090 if SAM 2 runs all 8 parts in same GPU context | Track one part at a time (loop in sam2_tracker.py), reinitialize state per part |
| ArUco detection (Task 10) | Gallery lighting (low lux, colored ambient) degrades ArUco reliability | Print markers at maximum contrast; test in actual gallery lighting before commissioning |
| Pixi.js line-art composite (Task 13) | WebM alpha channel may not decode correctly in all Chromium versions | Have PNG sequence fallback ready; use libvpx with yuva420p and auto-alt-ref 0 |
| Visual gate (Task 17) | Rigid mode shows "pasted-on" limb appearance at extreme walk poses | If severe, escalate to split_joints before approving 19-creature scale |
| 19-creature scale (post-Phase 1) | Flying creatures (butterfly, jellyfish) will fail rigid mode visually | Plan mesh_deform upgrade before authoring their parts_config.json |

---

## Sources

- `planning/specs/track2-sam2-hybrid_spec.md` — full architectural spec, edge case decisions, error handling
- `planning/specs/kiosk-ui_spec.md` — visitor UX flow and state machine
- `planning/specs/scan-pipeline_spec.md` — scan-watcher, bridge server, creature ID detection
- `planning/specs/scene-manager_spec.md` — projected display, creature spawning, depth layering
- `planning/specs/creature-behaviors_spec.md` — animation behaviors, Kling/SeedDance prompts, generation settings
- `planning/specs/color-extraction_spec.md` — original color-extraction approach (superseded by Track 2 for stroke fidelity)
- `planning/plans/2026-05-11-track2-sam2-hybrid.md` — 18-task implementation plan with full code
- Disney Research 2015: Live Texturing of AR Characters from Colored Drawings (referenced in spec as industry validation of decouple-animation-from-color approach)
- SAM 2 (Meta, 2024) — facebook/sam2 GitHub

---

*Feature research for: interactive art installation color-transfer pipeline (SAM 2 + Pixi.js)*
*Researched: 2026-05-11*
