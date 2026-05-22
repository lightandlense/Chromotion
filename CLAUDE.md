# Color Animals Interactive

Space-themed interactive coloring installation — visitors color pre-printed space creature templates, scan them at a kiosk, and watch their creature appear animated in a projected space environment alongside other visitors' creatures.

## Tech Stack
- Frontend: Pixi.js (sprite rendering, tinting, animation)
- Scanner: Browser getUserMedia API (webcam capture)
- Color Extraction: Canvas pixel sampling against predefined region maps
- Communication: localStorage events (kiosk → scene, same machine)
- Deploy: Local file (no server needed)

## Workspaces
- /planning — Specs, architecture, decisions
- /src — Application code
- /docs — Documentation
- /ops — Deployment and operations

## Routing
| Task | Go to | Read | Skills |
|------|-------|------|--------|
| Spec a feature | /planning | CONTEXT.md | — |
| Write code | /src | CONTEXT.md | — |
| Write docs | /docs | CONTEXT.md | — |
| Deploy or debug | /ops | CONTEXT.md | — |

## Two-screen architecture
- kiosk.html — Scanning station: webcam preview, scan button, color preview, submit
- scene.html — Projected display: animated creatures floating in star/planet environment

## Creature system
Each creature type has:
- A printable template PDF (predefined color regions outlined for coloring)
- A Pixi.js spritesheet with animation states (idle, drift, swim)
- A regions.json defining which pixel areas to sample for each color zone

## Vehicle system
Each vehicle type has:
- A printable lineart PNG (side-profile, black outlines on white)
- A `cadillac_parts.json` defining geometric masks (circle for wheels, complement for body)
- A dedicated kiosk page (e.g. `car_kiosk.html`) with its own scrolling environment
- No SAM2 — wheel masks are computed geometrically at runtime

## Naming conventions
- Specs: feature-name_spec.md
- Components: PascalCase (Scanner.js, SceneManager.js)
- Creature folders: kebab-case (space-whale/, star-ray/)
- Decision records: YYYY-MM-DD-decision-title.md
