/**
 * part_renderer.js — Pixi.js v7 renderer module
 *
 * Exports:
 *   init(scanId)          — Load motion data, pre-load line-art, load scan textures, start animation
 *   cleanupSession(state) — Destroy visitor scan textures, evict from Assets cache, restart ticker
 *
 * Coordinate system: 1920x1080 (matches motion_data.json frame_size)
 * Frame rate: 24fps via delta accumulator (display-refresh-agnostic)
 */

// PIXI is loaded via CDN script tag in kiosk.html before this module is imported.
// We reference window.PIXI directly.

const FRAME_COUNT = 121;
const CANVAS_W = 1920;
const CANVAS_H = 1080;

let _app = null; // singleton PIXI.Application

/**
 * Build a zero-padded frame filename like "frame_0042.png"
 */
function frameUrl(index) {
  const padded = String(index).padStart(4, '0');
  return `/src/animations/ram_lineart/frame_${padded}.png`;
}

/**
 * Build the array of all 121 line-art frame URLs.
 */
function buildLineArtUrls() {
  const urls = [];
  for (let i = 0; i < FRAME_COUNT; i++) {
    urls.push(frameUrl(i));
  }
  return urls;
}

/**
 * Ensure the PIXI.Application singleton exists.
 * Creates it on first call and appends the canvas to #canvas-container.
 */
function ensureApp() {
  if (_app) return _app;

  _app = new PIXI.Application({
    width: CANVAS_W,
    height: CANVAS_H,
    backgroundAlpha: 0,
    antialias: true,
    resolution: 1,
    autoDensity: false,
  });

  const container = document.getElementById('canvas-container');
  container.appendChild(_app.view);

  // Scale canvas to fit window while preserving 16:9 aspect ratio
  function scaleCanvas() {
    const scale = Math.min(
      window.innerWidth / CANVAS_W,
      window.innerHeight / CANVAS_H
    );
    _app.view.style.width = `${CANVAS_W * scale}px`;
    _app.view.style.height = `${CANVAS_H * scale}px`;
  }
  window.addEventListener('resize', scaleCanvas);
  scaleCanvas();

  return _app;
}

/**
 * init(scanId)
 *
 * 1. Fetch motion_data.json + parts_config.json in parallel
 * 2. Pre-load all 121 line-art frames (startup cost, not per-visitor)
 * 3. Pre-load 8 scan part textures for this visitor's scanId
 * 4. Build sprite hierarchy with correct z-order
 * 5. Start 24fps animation loop via delta accumulator
 *
 * Returns a state object passed to cleanupSession() later.
 */
export async function init(scanId) {
  const app = ensureApp();

  // Stop any running ticker from a previous session before rebuilding
  app.ticker.stop();
  // Clear stage from previous session
  while (app.stage.children.length > 0) {
    app.stage.removeChildAt(0);
  }

  // 1. Fetch config files in parallel
  const [motionData, partsConfig] = await Promise.all([
    fetch('/data/motion_data.json').then((r) => r.json()),
    fetch('/data/parts_config.json').then((r) => r.json()),
  ]);

  // 2. Build and pre-load all line-art frame URLs (once at startup)
  const lineArtUrls = buildLineArtUrls();
  await PIXI.Assets.load(lineArtUrls);

  // 3. Build scan texture URLs and pre-load them
  const partNames = partsConfig.parts_list; // preserve order from JSON
  const textureUrls = {};
  const textureUrlArray = [];
  for (const partName of partNames) {
    const url = `/data/scans/${scanId}/textures/${partName}.png`;
    textureUrls[partName] = url;
    textureUrlArray.push(url);
  }
  await PIXI.Assets.load(textureUrlArray);

  // 4. Build sprite container with sortable z-order
  const spriteContainer = new PIXI.Container();
  spriteContainer.sortableChildren = true;

  const sprites = {};
  for (const partName of partNames) {
    const texture = PIXI.Texture.from(textureUrls[partName]);
    const sprite = new PIXI.Sprite(texture);
    sprite.anchor.set(0.5, 0.5);
    sprite.zIndex = partsConfig.z_order[partName] ?? 0;
    spriteContainer.addChild(sprite);
    sprites[partName] = sprite;
  }
  spriteContainer.sortChildren(); // sort once after all sprites added

  app.stage.addChild(spriteContainer);

  // 5. Line-art composite layer — renders on top of all part sprites
  const lineArtContainer = new PIXI.Container();
  const lineArtSprite = new PIXI.Sprite(PIXI.Texture.from(lineArtUrls[0]));
  lineArtSprite.width = CANVAS_W;
  lineArtSprite.height = CANVAS_H;
  lineArtContainer.addChild(lineArtSprite);
  app.stage.addChild(lineArtContainer); // added AFTER spriteContainer → renders on top

  // 6. Animation ticker — delta accumulator for display-refresh-agnostic 24fps
  let currentFrame = 0;
  let frameAccum = 0;
  const framesPerAnimFrame = 60 / motionData.fps; // = 2.5 at 24fps

  app.ticker.add((delta) => {
    frameAccum += delta;
    if (frameAccum >= framesPerAnimFrame) {
      frameAccum -= framesPerAnimFrame;
      currentFrame = (currentFrame + 1) % motionData.frame_count;
    }

    // Update each part sprite position and rotation
    for (const partName of partNames) {
      const frameData = motionData.parts[partName]?.frames[currentFrame];
      if (!frameData || frameData.tracking_quality === 0) {
        // Skip this part this frame — hide it if quality is zero
        sprites[partName].visible = frameData ? false : true;
        continue;
      }
      sprites[partName].visible = true;
      sprites[partName].position.set(frameData.cx, frameData.cy);
      sprites[partName].rotation = frameData.angle;
    }

    // Swap line-art frame — synchronous cache hit after pre-load
    lineArtSprite.texture = PIXI.Texture.from(lineArtUrls[currentFrame]);
  });

  app.ticker.start();

  return {
    app,
    sprites,
    partNames,
    textureUrls,
    textureUrlArray,
    lineArtUrls,
    scanId,
  };
}

/**
 * cleanupSession(state)
 *
 * Destroys visitor scan textures and evicts them from the Assets cache.
 * Does NOT destroy line-art textures — they are static baked assets.
 * Restarts the ticker so the kiosk can accept the next visitor's scan.
 *
 * @param {object} state — return value from init()
 */
export async function cleanupSession(state) {
  const { app, partNames, scanId } = state;

  // Stop ticker during cleanup to prevent mid-cleanup frame renders
  app.ticker.stop();

  // Unload visitor scan textures via Assets (never destroy directly — crashes WebGL context)
  for (const partName of partNames) {
    const url = `/data/scans/${scanId}/textures/${partName}.png`;
    await PIXI.Assets.unload(url);
  }

  // Restart ticker so kiosk can accept next scan
  app.ticker.start();
}
