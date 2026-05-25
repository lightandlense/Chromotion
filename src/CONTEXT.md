# Current Project
Core application code for Color Animals Interactive. Two HTML entry points on the same machine:
- kiosk.html — scanning station (webcam, color extraction, submit)
- scene.html — projected display (animated creatures in space environment)

They communicate via localStorage events. Kiosk pushes a creature payload; scene receives it and spawns the creature.

# What good looks like
Clean separation: Scanner handles webcam/extraction, CreatureSpawner handles animation/placement, SceneManager manages live scene state. The localStorage message format is the only contract between kiosk and scene.

# What to avoid
Putting display logic in the kiosk or scanning logic in the scene. Keep them decoupled — they are separate browser windows on separate monitors.
