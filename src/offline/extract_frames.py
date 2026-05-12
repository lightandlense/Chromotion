"""
Extract JPEG frames from animation video for SAM 2 tracking.

SAM 2 init_state() requires a directory of JPEG frames named with zero-padded
integers (e.g., 0000.jpg, 0001.jpg ...). This script handles that extraction.

Usage:
    python src/offline/extract_frames.py \
        --video "src/animations/ram animation.mp4" \
        --output src/animations/ram_frames \
        --quality 2

    python src/offline/extract_frames.py --video <path> --output <dir>
"""
import argparse
import subprocess
import pathlib
import sys


def extract_frames(
    video_path: str,
    output_dir: str,
    quality: int = 2,
    fps: float = None,
) -> int:
    """
    Extract frames from video to JPEG files using ffmpeg.

    Args:
        video_path: Path to source video file.
        output_dir: Directory to write JPEG frames to.
        quality: JPEG quality scale (1=best, 31=worst). Default 2 is near-lossless.
        fps: If set, force specific fps (useful for resampling). Default: video native fps.

    Returns:
        Number of frames extracted.

    Raises:
        FileNotFoundError: If video file doesn't exist.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    video_path = pathlib.Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-i", str(video_path), "-q:v", str(quality)]
    if fps is not None:
        cmd += ["-r", str(fps)]
    cmd.append(str(output_dir / "%04d.jpg"))

    print(f"Extracting frames from: {video_path}")
    print(f"Output directory: {output_dir}")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)

    frame_count = len(list(output_dir.glob("*.jpg")))
    print(f"Extracted {frame_count} frames.")
    return frame_count


def main():
    parser = argparse.ArgumentParser(description="Extract JPEG frames for SAM 2 tracking")
    parser.add_argument("--video", required=True, help="Source video file path")
    parser.add_argument("--output", required=True, help="Output directory for JPEG frames")
    parser.add_argument("--quality", type=int, default=2, help="JPEG quality 1-31 (1=best)")
    parser.add_argument("--fps", type=float, default=None, help="Force output FPS (default: native)")
    args = parser.parse_args()

    count = extract_frames(args.video, args.output, args.quality, args.fps)
    print(f"Done. {count} frames in {args.output}")


if __name__ == "__main__":
    main()
