# Creature Behaviors — Spec

## Purpose
Define the animation behavior states for each creature, including Kling/SeedDance generation prompts for producing the base animations from the standing still coloring page image.

---

## Animation Approach

Creatures are animated using Kling or SeedDance — AI video generation tools that animate a still image from a text prompt. The workflow:

1. Generate the coloring page still image (Adobe Firefly, standing still pose)
2. Color extraction regions are defined against this still image
3. The still image (with or without user colors applied) is fed into Kling/SeedDance with a behavior prompt
4. The output video becomes the creature's animation asset in the scene

Base animations are pre-generated once per creature. User colors are either:
- **Option A (preferred):** Applied to the still image first, then animated — each visitor gets a unique animation (generation takes 1-2 min, shown as "your creature is awakening")
- **Option B (fallback):** Pre-generate a single animation per creature type and apply colors as a post-process overlay

---

## Behavior States Per Creature

Each creature has:
- **Idle** — default looping motion
- **Action** — occasional triggered behavior (every 8-15 seconds, randomized)
- **Kling/SeedDance prompt** — text prompt to generate the animation from the standing still image

---

### SPACE CREATURES

#### Space Whale (01)
- **Idle:** Slow drift forward, gentle tail undulation, fins wave softly
- **Action:** Exhales a spout of glowing stardust upward, then resumes drift
- **Kling prompt:** `cosmic whale slowly swimming through deep space, gentle tail movement, fins waving, majestic and peaceful, loop`

#### Space Jellyfish (02)
- **Idle:** Bell pulses rhythmically, tentacles trail and drift behind
- **Action:** Propels upward in a quick pulse burst, then floats back down
- **Kling prompt:** `space jellyfish floating in space, bell pulsing gently, long tentacles drifting, bioluminescent, loop`

#### Space Manta Ray (03)
- **Idle:** Wide, slow banking glide, wings gently undulating
- **Action:** Banking turn — sweeps one direction then levels out
- **Kling prompt:** `cosmic manta ray gliding through space, wings undulating slowly, graceful banking movement, loop`

#### Space Octopus (04)
- **Idle:** Float in place, tentacles gently curl and uncurl
- **Action:** One tentacle extends outward, touches nothing, retracts
- **Kling prompt:** `space octopus floating in zero gravity, tentacles gently moving and curling, calm and curious, loop`

#### Space Butterfly (05)
- **Idle:** Slow flap cycle, gentle drift forward
- **Action:** Wings fully extend and hold for 2 seconds (display pose), then resume flapping
- **Kling prompt:** `cosmic butterfly slowly flapping wings in space, drifting gently forward, wings full of nebula patterns, loop`

#### Space Dragon — Shen Long style (06)
- **Idle:** Serpentine body undulates as it drifts forward, mane flows
- **Action:** Opens mouth, exhales a brief stream of cosmic fire/stardust
- **Kling prompt:** `Shen Long cosmic dragon slowly flying through space, long serpentine body undulating, mane flowing, majestic, loop`

#### Space Crab (07)
- **Idle:** Slowly drifts sideways, legs move gently
- **Action:** Both claws open and snap once, then return to resting
- **Kling prompt:** `cosmic crab floating in space, legs gently moving, drifting sideways slowly, loop`

---

### ZODIAC CREATURES

#### Aries — Ram (08)
- **Idle:** Standing, slow breath movement, ears flick, tail sways
- **Action:** Lowers head briefly as if about to charge, snorts, lifts back up
- **Kling prompt:** `cosmic ram standing still in space, breathing gently, ears flicking, brief head dip as if ready to charge, loop`

#### Taurus — Bull (09)
- **Idle:** Standing, slow breath, tail swishes
- **Action:** Head dips down as if grazing, lifts back up slowly
- **Kling prompt:** `cosmic bull standing in space, breathing slowly, tail swishing, head dips down to graze then lifts back up, loop`

#### Gemini — Twins (10)
- **Idle:** Two figures float side by side, both sway gently in unison
- **Action:** Figures turn to face each other briefly, then return to forward position
- **Kling prompt:** `twin cosmic figures floating in space side by side, gently swaying in unison, turning to look at each other then back, loop`

#### Cancer — Crab (11)
- **Idle:** Float, legs move gently, claws rest
- **Action:** Claws open and close once
- **Kling prompt:** `cosmic crab floating in space, legs gently moving, claws slowly opening and closing, loop`

#### Leo — Lion (12)
- **Idle:** Standing, chest rises and falls, tail sways, mane ripples
- **Action:** Opens mouth in a silent roar, mane flares outward, settles
- **Kling prompt:** `cosmic lion standing proud in space, mane flowing, breathing, opens mouth in a majestic roar then settles, loop`

#### Virgo — Celestial Maiden (13)
- **Idle:** Robes drift gently, hair flows, one hand holds wheat bundle
- **Action:** Raises free hand slowly, stardust flows from palm, lowers hand
- **Kling prompt:** `celestial cosmic maiden floating in space, robes gently flowing, raises hand and stardust pours from palm, loop`

#### Libra — Cosmic Scales (14)
- **Idle:** Scales float, gently sway left and right in balance
- **Action:** One side dips lower, then slowly returns to level
- **Kling prompt:** `ornate cosmic scales floating in space, gently tipping left then right, slowly returning to balance, loop`

#### Scorpio — Scorpion (15)
- **Idle:** Standing, legs shift slightly, tail sways
- **Action:** Tail arches up slowly to full strike position, holds, lowers
- **Kling prompt:** `cosmic scorpion standing in space, legs shifting, tail slowly arching up to strike position then lowering, loop`

#### Sagittarius — Centaur (16)
- **Idle:** Standing, horse body shifts weight, human torso sways
- **Action:** Raises bow, draws back slowly, releases (comet arrow fires off screen)
- **Kling prompt:** `cosmic centaur standing in space, horse body shifting weight, raises bow draws back and releases a glowing arrow, loop`

#### Capricorn — Sea-Goat (17)
- **Idle:** Fish tail undulates slowly, goat half stays upright
- **Action:** Dips forward as if diving, fish tail crests upward, returns to upright
- **Kling prompt:** `cosmic sea-goat floating in space, fish tail slowly undulating, dips forward briefly then returns upright, loop`

#### Aquarius — Water Bearer (18)
- **Idle:** Figure floats, robes drift, trickle of stars pours from urn continuously
- **Action:** Tilts urn further — stream of stars increases briefly, then returns to trickle
- **Kling prompt:** `cosmic figure floating in space pouring a stream of stars from an urn, robes drifting, tilts urn further then back, loop`

#### Pisces — Two Fish (19)
- **Idle:** Two fish slowly orbit each other in a circle
- **Action:** Both fish speed up the orbit briefly, then slow back down
- **Kling prompt:** `two cosmic fish swimming in a slow circle around each other in space, speeding up briefly then slowing again, loop`

---

## Generation Settings (Kling / SeedDance)

- **Duration:** 4-6 seconds (loops seamlessly)
- **Style prompt addition:** `space background, cosmic, glowing, coloring book line art style, clean outlines, whimsical`
- **Loop:** Enable seamless loop if supported
- **Resolution:** 1080×1080 or 1920×1080

---

## Files

| File | Purpose |
|------|---------|
| `src/creatures/[id]/animation.mp4` | Base animation video per creature |
| `src/creatures/[id]/creature.json` | Behavior config (timing, action probability) |
