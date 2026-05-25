# Scene Manager — Spec

## Purpose
Manage the projected display screen: a deep-space environment with animated, user-colored creatures floating and drifting through stars and planets. Receives new creature payloads from the kiosk and spawns them into the live scene.

---

## Scene Environment

The background is a parallax star field with 2-3 distant planets. All background elements are static assets or very slowly animated (stars twinkle, nebula drifts).

**Layers (back to front):**
1. Deep background — static starfield image
2. Far planets — large blurred planet images, drift very slowly (0.02 speed)
3. Nebula/dust — semi-transparent colored clouds, slow drift
4. Far creatures — creatures at low depthScale (0.5-0.7), smaller and slightly dimmer
5. Mid creatures — creatures at depthScale (0.7-0.9)
6. Near creatures — creatures at depthScale (0.9-1.0), full size and brightness
7. Foreground overlay — optional vignette, title text

---

## Creature Spawning

When a new creature payload arrives:
1. Pick a random spawn point along the edge of the canvas (any edge)
2. Assign a random depth value within the creature's `depthRange`
3. Scale the creature sprite by `depthScale * creature.scale`
4. Set opacity: `0.6 + (depthScale * 0.4)` — far creatures are dimmer
5. Apply user colors to each color layer via Pixi.js tint
6. Start the `idle` animation
7. Assign an initial heading pointing generally toward the scene center

**Maximum creatures:** 30. When the limit is reached, the oldest creature fades out over 2 seconds before the new one spawns.

---

## Creature Movement

Each creature has a heading (angle in radians) and a speed (from creature.json * depthScale).

Every frame:
1. Move creature by `speed * delta` in the heading direction
2. Every 3-8 seconds (randomized per creature): apply a small random heading adjustment (-0.3 to +0.3 radians)
3. If the creature reaches within 50px of the canvas edge, smoothly steer heading back toward center
4. Switch between `idle` and `swim` animations based on speed delta

Creatures do not collide with each other — they overlap freely.

---

## localStorage Listener

The scene listens for storage events on the key `color-animals:new-creature`.

```js
window.addEventListener('storage', (e) => {
  if (e.key === 'color-animals:new-creature') {
    const payload = JSON.parse(e.newValue);
    spawnCreature(payload);
    localStorage.removeItem('color-animals:new-creature');
  }
});
```

The payload format is defined in `localStorage-contract_spec.md`.

---

## Performance

- Target: 60fps with up to 30 creatures
- Pixi.js WebGL renderer handles sprite batching automatically
- Limit animated star particles to 200
- Preload all creature spritesheets at startup — no runtime loading delays

---

## Scene States

| State | Description |
|-------|-------------|
| `loading` | Preloading assets, show loading screen |
| `idle` | No creatures yet. Show "Color a creature at the kiosk!" prompt |
| `active` | Creatures present, normal scene |
| `full` | At creature limit, oldest creature begins fade-out |

---

## Files
- `src/components/SceneManager.js` — main scene controller
- `src/components/CreatureSpawner.js` — handles spawning, tinting, movement
- `src/components/Background.js` — star field and planet layers
- `scene.html` — entry point, initializes Pixi.js app and SceneManager
