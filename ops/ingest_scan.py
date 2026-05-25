"""
ingest_scan.py — Feed any scan image directly into the kiosk without a running server.

Usage:
  python ops/ingest_scan.py src/animations/car/crayon_scan.jpg

Opens car2_kiosk_test.html automatically. Refresh the page to see the result.
"""
import sys
import uuid
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.offline.mask_car2_scan import mask_scan

scan_path = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJECT_ROOT / "src/animations/car/crayon_scan.jpg"

scan_id = uuid.uuid4().hex[:8]
scan_dir = PROJECT_ROOT / "data" / "scans" / scan_id
scan_dir.mkdir(parents=True, exist_ok=True)

output_path = scan_dir / "car2_body.png"
mask_scan(scan_path, output_path)

latest = PROJECT_ROOT / "data" / "scans" / "latest_scan_id.txt"
latest.write_text(scan_id)
print(f"  scan_id: {scan_id}")
print(f"  Open http://localhost:8000/src/runtime/car2_kiosk_test.html and it will auto-load.")
