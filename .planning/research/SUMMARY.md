# Project Research Summary

**Project:** Color Animals Interactive
**Domain:** SAM 2 offline video segmentation + Pixi.js sprite renderer -- interactive art installation kiosk
**Researched:** 2026-05-11
**Confidence:** HIGH (offline pipeline architecture and stack); MEDIUM (kiosk deployment edge cases)

## Executive Summary

Color Animals Interactive is a public kiosk installation where visitors color printed creature drawings, scan them, and see their exact crayon artwork appear on an animated creature projected on a wall. The expert approach separates all computation-heavy work (SAM 2 video segmentation, motion data baking) into a one-time offline pipeline, leaving only lightweight image operations (ArUco scan rectification, PNG mask slicing) in the runtime path. This offline-heavy architecture is the non-negotiable design decision: it is the only way to hit the sub-3-second scan-to-display requirement while delivering per-pixel color fidelity.

The recommended approach validates with one creature (ram) before scaling to 19. The offline pipeline uses SAM 2 (sam2.1_hiera_large checkpoint) to track all body parts across 121 animation frames, producing a motion_data.json contract file and per-part rest-pose masks. At runtime, OpenCV ArUco markers on the coloring sheet provide homography for perspective correction, scipy/Pillow apply the rest-pose masks to slice the scan into per-part RGBA textures, and Pixi.js v7 drives sprite transforms from the pre-baked data. The line art from the Firefly animation composites on top as a PNG sequence, preserving dark crayon colors that brightness-threshold approaches would erase.

The critical risk cluster is all in the offline bake phase: SAM 2 VRAM accumulation will OOM a consumer GPU if multiple body parts are tracked in a single session; click prompt placement errors silently produce wrong masks that only fail at visual review; angle wrap-around in the serialized motion data causes snap artifacts in the final animation. Every one of these is preventable with upfront discipline in the bake script. The runtime path has its own risks (Pixi.js texture leaks across visitor sessions, WebGL context loss after hours of operation) but these are well-understood patterns with established solutions.

## Key Findings

### Recommended Stack

The stack is determined by two hard constraints: SAM 2 requires Python 3.11 + PyTorch 2.5.1 + CUDA 12.1 (exact versions, not approximate), and the existing Pixi.js codebase uses v7 sprite child hierarchies that v8 breaks. On Windows, SAM 2 must be installed with SAM2_BUILD_CUDA=0 to skip the CUDA extension build -- the extension does not affect tracking quality and the Windows NVCC build chain is unreliable. opencv-contrib-python==4.10.0.84 is mandatory; the base opencv-python package lacks ArUco bindings in 4.10+.

**Core technologies:**
- Python 3.11 + PyTorch 2.5.1 + CUDA 12.1: SAM 2 offline pipeline -- exact versions required; 3.12 and numpy 2.x both have compatibility gaps with this ML stack
- SAM 2 1.1.0 (sam2.1_hiera_large checkpoint): Per-part mask tracking across 121 frames -- only production-grade zero-shot video segmentation model; bakes motion data offline so zero cost at runtime
- opencv-contrib-python 4.10.0.84: ArUco detection + homography rectification -- contrib variant mandatory; base opencv-python 4.10+ has incomplete ArUco Python bindings
- Pixi.js 7.4.2: Runtime sprite renderer with data-driven animation loop -- v8 breaks Sprite child hierarchies; v7 is the last compatible version for the existing codebase
- orjson 3.x: Serialization of motion_data.json -- native numpy support, 15x faster than stdlib, human-readable (unlike msgpack) for debugging transforms
- scipy.ndimage.binary_dilation: 15px mask dilation -- integrates cleanly with numpy mask arrays from SAM 2 without conversion round-trips

### Expected Features

**Must have (table stakes):**
- Visitor exact crayon colors and stroke texture appear on the animated creature -- any generic palette or flat tint fails the core value proposition
- Sub-3-second scan-to-display time -- gallery context; visitors lose interest fast, long waits read as broken
- ArUco homography rectification -- webcam angle is never perfectly orthogonal; without this, colors land in wrong regions
- SAM 2 offline tracking + rest-pose mask bake -- foundation for all rendering; cannot run at runtime
- Transparent line-art composite on top of colored sprites -- preserves dark crayon colors that would otherwise be obliterated
- Graceful scan failure with retry prompt -- ArUco detection will fail under bad lighting or awkward angles; must not crash

**Should have (differentiators):**
- Exact stroke texture fidelity including hatching, pressure variation, out-of-line marks -- separates this from generic color-by-region kiosks
- Dark colors render faithfully (black, navy, deep purple) -- competing approaches use brightness gates that erase dark colors
- Outlier auto-interpolation for SAM 2 jitter frames -- prevents visible animation glitches without manual intervention
- Click-prompt authoring tool with Tkinter UI -- interactive seed point placement for SAM 2; cannot be guessed or automated without human judgment

**Defer to post-Phase-1:**
- split_joints and mesh_deform render modes -- escalate only if rigid mode fails the Task 17 visual gate
- motion_review_tool manual brush correction -- only needed if auto-interpolation misses multi-frame SAM 2 drift blocks
- Projector output formatting -- hardware not yet selected; blocks no software validation
- 19-creature scale authoring -- gate on Phase 1 ram approval
- mesh_deform render mode -- required for flying creatures (butterfly, jellyfish) but not relevant until 19-creature scale

### Architecture Approach

The system divides cleanly into two worlds that communicate only through two contract files: motion_data.json (all frame/part transforms) and rest_pose_masks (RGBA dilated masks at rest pose). The offline world runs once per creature on a dev machine with a GPU. The runtime world runs per visitor on the kiosk with no ML inference. Everything else -- SAM 2 model, raw frames, intermediate masks -- lives exclusively offline. The Pixi.js renderer is purely data-driven: it reads the motion JSON, pre-loads all textures, then drives sprite position and rotation per frame from cached data. No GPU model is ever loaded at runtime.

**Major components:**
1. sam2_part_tracker.py -- Track all creature body parts across all 121 animation frames in a single SAM 2 propagation pass; produce motion_data.json and rest_pose_masks; runs offline once per creature
2. scan_rectify.py + scan_slice.py -- ArUco homography correction then per-part RGBA texture extraction using rest_pose_masks; the entire runtime Python path, must complete in under 3 seconds total
3. part_renderer.js (Pixi.js v7) -- Data-driven animation loop; loads motion_data.json, pre-loads all part textures, drives sprite transforms per frame, composites line art PNG sequence as topmost layer
4. click_prompt_tool.py -- Tkinter UI for authoring parts_config.json (SAM 2 seed points, z-order, render mode); one-time authoring step that gates the entire offline pipeline
5. outlier_fixer.py -- Auto-interpolation of single-frame centroid jumps flagged by tracking_quality threshold; prevents visible animation glitches without manual correction

### Critical Pitfalls

1. **SAM 2 VRAM accumulation OOM** -- Track one body part per SAM 2 session; call reset_state() and torch.cuda.empty_cache() between parts; use hiera_tiny/small during development, reserve hiera_large for final bake only
2. **Angle wrap-around in motion_data.json** -- Apply numpy.unwrap() to the full angle sequence per part before serialization; add a validation step flagging any frame-to-frame delta above 1.0 radian; never store raw atan2 output
3. **Click prompt mask leakage into adjacent parts** -- Use bounding box prompts (not point prompts) for thin limbs; place clicks at geometric centroids not near boundaries; visually inspect every rest_pose_mask before baking; add negative clicks when leakage appears
4. **Pixi.js texture memory leak across visitor sessions** -- Use a SessionTextureManager that calls texture.destroy(true) on all visitor textures at session end; never use Texture.from() (global cache) for visitor textures; run a 4-hour soak test before venue opening
5. **CORS blocking texture loads in kiosk deployment** -- Always serve from a local HTTP server launched by a startup .bat file; never open index.html via file:// protocol; test on a clean venue machine before opening

## Implications for Roadmap

Based on research, the dependency chain is clear: parts_config.json must exist before SAM 2 can run; motion_data.json and rest_pose_masks must exist before the runtime can start; ArUco rectification must work before scan slicing can produce useful textures. This dictates a strict phase order.

### Phase 1: Offline Pipeline and Single-Creature Bake (Ram)

**Rationale:** Everything downstream depends on having correct baked data. The authoring tool, SAM 2 tracking, and outlier correction must all be working and validated before any runtime code is meaningful. This phase has the highest density of critical pitfalls (OOM, angle wrap, mask leakage, rest-pose frame selection) and needs the most careful attention.

**Delivers:** Validated motion_data.json and rest_pose_masks for the ram; parts_config.json; working offline pipeline scripts

**Addresses:** Click-prompt authoring, SAM 2 tracking, outlier auto-interpolation, rest-pose mask bake, make_lineart_video.py

**Avoids:** SAM 2 VRAM OOM (one-part-per-session pattern), angle wrap-around (numpy.unwrap in bake script), click prompt leakage (visual verification gate before commit)

**Research flag:** STANDARD PATTERNS -- SAM 2 API and multi-part tracking are well-documented. Follow the single-pass multi-object propagation pattern exactly as specified in ARCHITECTURE.md.

### Phase 2: Runtime Scan Pipeline

**Rationale:** Once baked data exists, the runtime scan path can be built and timed against the 3-second gate. ArUco rectification and scan slicing are independent of the renderer and can be validated with static test inputs before the full Pixi.js integration.

**Delivers:** scan_rectify.py (ArUco homography, ORB fallback), scan_slice.py (per-part RGBA textures), process_scan.py CLI (end-to-end in one command), performance gate validation

**Addresses:** Scan-to-display budget, graceful failure prompts, uncolored region handling, CORS/server startup

**Avoids:** ArUco detection failure (DICT_4X4_50 dictionary, CLAHE normalization, homography det validation), CORS blocking (local HTTP server startup script)

**Research flag:** STANDARD PATTERNS -- ArUco homography and image masking are mature, well-documented OpenCV operations.

### Phase 3: Pixi.js Renderer and Visual Gate

**Rationale:** With correct baked data and a working scan pipeline, the renderer can be built and connected end-to-end. This phase ends with the Russell visual approval gate (Task 17) that determines whether rigid mode is sufficient or split_joints escalation is needed.

**Delivers:** track2_renderer.js (Pixi.js v7 data-driven sprite animation, line-art composite), SessionTextureManager, WebGL context loss recovery, end-to-end scan-to-display demo, visual quality gate decision

**Addresses:** Exact color fidelity, dark color rendering, line-art overlay, z-order correctness, video sync (defaulting to PNG sequence to avoid video clock drift)

**Avoids:** Texture memory leak (SessionTextureManager with destroy(true)), WebGL context loss (contextlost/contextrestored handlers), video frame sync mismatch (PNG sequence as default path)

**Research flag:** MODERATE COMPLEXITY -- Pixi.js v7 sprite API is documented. The SessionTextureManager pattern and context loss recovery need deliberate implementation. The 4-hour soak test is non-negotiable before venue deployment.

### Phase 4: 19-Creature Scale

**Rationale:** Only after the Task 17 visual gate approves rigid mode for the ram does it make sense to author parts_config.json for the remaining 18 creatures. Flying creatures (butterfly, jellyfish, manta ray) will require mesh_deform render mode -- a known scope addition but should not be built until the base architecture is validated.

**Delivers:** motion_data.json and rest_pose_masks for all 19 creatures; escalated render modes (split_joints, mesh_deform) where needed; kiosk hardware integration; projector output formatting; shared projected scene with up to 30 concurrent visitor creatures

**Addresses:** 19-creature authoring, mesh_deform for wing flex, projector calibration, multiplayer scene depth layering

**Research flag:** NEEDS DEEPER RESEARCH -- mesh_deform render mode has unknown engineering cost. Plan a dedicated research spike (2-3 days) before authoring flying creature parts_config.json. Kiosk hardware integration depends on hardware selection not yet locked.

### Phase Ordering Rationale

- The offline/runtime split is non-negotiable: motion_data.json must exist before any runtime code is meaningful, which forces Phase 1 before Phase 2
- Scan pipeline (Phase 2) is validated with static test inputs before connecting to the renderer (Phase 3) -- this isolates timing failures to the correct component
- The visual gate at the end of Phase 3 is a genuine go/no-go decision point: rigid mode approval for the ram before committing to 19-creature authoring avoids 19x the rework if the approach needs architectural changes
- Flying creatures are explicitly deferred because mesh_deform is a meaningfully different engineering problem; mixing it into the initial scale-up would make Phase 4 unbounded

### Research Flags

Phases needing deeper research during planning:
- **Phase 4 (mesh_deform):** No existing implementation or cost estimate; needs a dedicated research spike before any flying creature is authored. Unknown if mesh_deform can share the same JSON contract or requires a different schema.
- **Phase 4 (kiosk hardware):** Hardware selection not yet locked. Camera mount, enclosure design, projector model, and physical button integration are all unknowns that will affect software integration points.

Phases with standard patterns (skip research-phase):
- **Phase 1:** SAM 2 video predictor API is well-documented with official examples. Follow the single-pass multi-object pattern.
- **Phase 2:** ArUco homography, scipy dilation, and Pillow RGBA slicing are mature, well-documented operations.
- **Phase 3:** Pixi.js v7 sprite API is documented. The non-standard elements (SessionTextureManager, context loss recovery) have established community patterns from the GitHub issues cited in PITFALLS.md.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified via official PyPI, GitHub, and npm; SAM 2 + PyTorch compatibility matrix confirmed; Pixi.js v8 breaking change confirmed via migration guide |
| Features | HIGH | Derived from full internal spec suite (6 specs + implementation plan); no external speculation needed |
| Architecture | HIGH | SAM 2 API verified via official repo + deepwiki; Pixi.js v7 API verified via official docs; offline/runtime split validated by the 3-second budget constraint |
| Pitfalls | MEDIUM-HIGH | SAM 2 VRAM/OOM: HIGH (confirmed via GitHub issues #258, #118); ArUco + kiosk lighting: MEDIUM (community reports, not controlled benchmarks); Pixi.js memory: HIGH (confirmed via official GC docs + issue #2220) |

**Overall confidence:** HIGH for Phase 1-3 implementation decisions. MEDIUM for Phase 4 scope (hardware and mesh_deform).

### Gaps to Address

- **mesh_deform render mode cost:** Unknown engineering cost; no existing implementation to reference. Address by running a time-boxed spike (2-3 days) before committing to Phase 4 scope.
- **Venue lighting conditions for ArUco:** ArUco detection reliability under actual gallery lighting is only confirmed by a physical test at the venue. The 99% detection rate gate must be validated in situ, not on a developer desk.
- **Kiosk hardware spec:** Camera model, projector throw distance, and enclosure design affect software integration points. These need to be locked before Phase 4 begins.
- **SAM 2 VRAM on the specific dev machine GPU:** If the offline bake machine has 4GB VRAM or less, hiera_large is not usable and hiera_small becomes the production checkpoint, with an associated quality tradeoff to assess.

## Sources

### Primary (HIGH confidence)
- facebookresearch/sam2 GitHub -- INSTALL.md, API, checkpoint sizes, Windows notes
- SAM 2 deepwiki (deepwiki.com/facebookresearch/sam2) -- video predictor API patterns
- OpenCV ArUco 4.x docs (docs.opencv.org) -- ArucoDetector class API
- PixiJS v8 Migration Guide (pixijs.com/8.x/guides/migrations/v8) -- Sprite child hierarchy breaking change confirmed
- pixi.js npm -- v7.4.2 latest v7 stable confirmed
- Pixi.js Garbage Collection Official Docs -- texture destroy(true) pattern
- Pixi.js Texture Memory Leak GitHub Issue #2220 -- memory leak confirmed
- WebGL Handling Context Lost Khronos Official -- contextlost/contextrestored recovery pattern
- Internal specs: track2-sam2-hybrid_spec.md, kiosk-ui_spec.md, scan-pipeline_spec.md, scene-manager_spec.md, creature-behaviors_spec.md, color-extraction_spec.md

### Secondary (MEDIUM confidence)
- SAM 2 VRAM OOM HuggingFace Discussion -- VRAM accumulation pattern confirmed by community
- SAM 2 GPU Memory Not Released GitHub Issue #258 -- reset_state workaround confirmed
- SAM2Long Long Video Mask Drift ICCV 2025 -- looping animation drift documented in research
- ArUco Low Light Performance OpenCV Issue #26686 -- CLAHE normalization recommendation
- Pixi.js WebGL Context Loss GitHub Issue #6494 -- context loss recovery pattern
- Pixi.js CORS Local File GitHub Issue #7552 -- file:// blocking confirmed
- Disney Research 2015 Live Texturing of AR Characters -- industry validation of decouple-animation-from-color approach

### Tertiary (LOW confidence)
- Community reports on ArUco detection rates under venue lighting -- needs physical validation at actual installation site

---
*Research completed: 2026-05-11*
*Ready for roadmap: yes*
