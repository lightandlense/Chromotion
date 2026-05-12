"""
Export animation line art as per-frame PNG sequence for Pixi.js renderer overlay.

The line art frames are composited on top of all colored part sprites in the renderer,
preserving dark crayon colors (black, navy, deep purple) that brightness-threshold
approaches would erase.

Requirements:
- OFFLINE-08: Export as transparent WebM + per-frame PNG sequence

Usage:
    python src/offline/make_lineart_video.py \\
        --source "src/animations/ram_animation_alpha.webm" \\
        --output src/animations/ram_lineart \\
        --has-alpha

    python src/offline/make_lineart_video.py \\
        --source "src/animations/ram animation.mp4" \\
        --output src/animations/ram_lineart
"""
import argparse
import subprocess
import pathlib
import sys


def export_png_sequence(
    source_path: str,
    output_dir: str,
    has_alpha: bool = False,
    start_number: int = 0,
) -> int:
    """
    Export animation frames as RGBA PNG sequence.

    Args:
        source_path: Path to source video (MP4 or WebM).
        output_dir: Directory to write PNG frames to.
        has_alpha: True if source video has alpha channel (e.g., WebM VP8/VP9+alpha).
        start_number: Frame number offset for naming (default 0 = frame_0000.png).

    Returns:
        Number of frames exported.
    """
    source_path = pathlib.Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source not found: {source_path}")

    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = str(output_dir / "frame_%04d.png")

    if has_alpha:
        # VP8+alpha WebM: must use libvpx decoder explicitly to extract the invisible
        # alpha frame track. Without -vcodec libvpx, ffmpeg ignores the alpha stream.
        cmd = [
            "ffmpeg", "-y",
            "-vcodec", "libvpx",
            "-i", str(source_path),
            "-pix_fmt", "rgba",
            "-start_number", str(start_number),
            output_pattern,
        ]
    else:
        # MP4 without alpha: apply colorkey filter to convert white background to transparent.
        # fuzz=0.15 means colors within 15% brightness of white become transparent.
        # similarity=0.05 controls the edge softness.
        cmd = [
            "ffmpeg", "-y",
            "-i", str(source_path),
            "-vf", "colorkey=0xffffff:0.15:0.05",
            "-pix_fmt", "rgba",
            "-start_number", str(start_number),
            output_pattern,
        ]

    print(f"Exporting frames from: {source_path}")
    print(f"Has alpha channel: {has_alpha}")
    print(f"Output: {output_dir}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg error: {e.stderr}", file=sys.stderr)
        raise

    frames = sorted(output_dir.glob("frame_*.png"))
    print(f"Exported {len(frames)} frames.")
    return len(frames)


def export_webm(source_path: str, output_path: str) -> None:
    """
    Export animation as transparent WebM (VP9+alpha) — secondary/archival path.

    Note: Pixi.js renderer defaults to PNG sequence to avoid video sync issues.
    WebM export is for archival/fallback only.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source_path),
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",  # VP9 with alpha
        "-b:v", "0",
        "-crf", "30",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    print(f"WebM exported: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Export animation line art as PNG sequence for Pixi.js overlay"
    )
    parser.add_argument("--source", required=True, help="Source video file path")
    parser.add_argument("--output", required=True, help="Output directory for PNG frames")
    parser.add_argument(
        "--has-alpha", action="store_true",
        help="Source video has alpha channel (e.g., VP8/VP9+alpha WebM)"
    )
    parser.add_argument(
        "--webm-out", default=None,
        help="Optional: also export as transparent WebM at this path"
    )
    args = parser.parse_args()

    count = export_png_sequence(args.source, args.output, args.has_alpha)
    print(f"Done. {count} PNG frames written to {args.output}")

    if args.webm_out:
        export_webm(args.source, args.webm_out)
        print(f"WebM also written to {args.webm_out}")


if __name__ == "__main__":
    main()
