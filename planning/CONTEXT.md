# Current Project
Building the Cadillac car kiosk — a new "vehicles" mode inside Color Animals Interactive. A child prints and colors a 1959 Cadillac lineart template, scans it at the kiosk, and their colored car drives across a scrolling city background in an infinite loop. Wheels spin proportional to car speed.

# What good looks like
- Spec in planning/specs/ covers all implementation decisions
- mask_car_parts.py produces clean RGBA crops for body and both wheels from a rectified scan
- car_kiosk.html runs at 1920x1080, car loops smoothly, parallax city feels convincing
- Full flow (print → color → scan → animate) works end to end with one calibration pass for wheel geometry

# What to avoid
- Don't use SAM2 for vehicles — geometric circle masks are sufficient and far simpler
- Don't modify existing creature pipeline files — vehicle mode is additive only
- Don't hardcode wheel pixel coordinates without a calibration step after first real scan
