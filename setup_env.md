# Offline Pipeline Environment Setup

## Prerequisites
- Anaconda or Miniforge installed
- NVIDIA GPU with CUDA 12.1+ (optional; CPU fallback works for smoke test)
- Git

## Steps

### 1. Create conda environment
```powershell
conda create -n color-animals python=3.11 -y
conda activate color-animals
```

### 2. Install PyTorch (MUST be before SAM 2)
```powershell
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cu121
```

### 3. Clone and install SAM 2 (CUDA extension skipped — safe for offline tracking)
```powershell
git clone https://github.com/facebookresearch/sam2.git vendor/sam2
cd vendor/sam2
$env:SAM2_BUILD_CUDA = "0"
pip install -e .
cd ..\..
```

### 4. Install remaining dependencies
```powershell
pip install opencv-contrib-python==4.10.0.84
pip install numpy==1.26.4 scipy pillow tqdm orjson pytest
```

### 5. Download SAM 2.1 checkpoints
Place checkpoints in `vendor/sam2/checkpoints/`:
- Production bake: `sam2.1_hiera_large.pt` (~900MB)
  URL: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_large.pt
- Dev/smoke test: `sam2.1_hiera_tiny.pt` (~155MB)
  URL: https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt

### 6. Verify installation
```powershell
python -c "from sam2.build_sam import build_sam2_video_predictor; print('SAM 2 OK')"
python -c "import cv2; print('OpenCV:', cv2.__version__); print('ArUco:', cv2.aruco)"
python -c "import orjson, pytest, torch; print('torch:', torch.__version__)"
```

## Notes

- Do NOT install `opencv-python` (base package). Only `opencv-contrib-python==4.10.0.84` is correct.
  If both are installed in the same env, pip will silently override ArUco bindings.
- `SAM2_BUILD_CUDA=0` skips the CUDA extension build. This does NOT affect tracking quality —
  SAM 2 uses CUDA via PyTorch's built-in CUDA support, not a custom extension.
- If GPU VRAM is <= 4GB, substitute `sam2.1_hiera_small.pt` for production bake (quality tradeoff).
- Run smoke tests after setup: `pytest tests/preprocess/test_sam2_smoke.py -v`
