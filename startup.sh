#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONUNBUFFERED=1

# Use the env python directly (set in Dockerfile)
PY="${COMFY_ENV_PY:-/root/miniconda3/envs/comfyui/bin/python}"

echo "[startup] Python: $($PY -V 2>&1)"
echo "[startup] PWD: $(pwd)"
echo "[startup] USE_CPU=${USE_CPU:-false}"
echo "[startup] COMFY_PORT=${COMFY_PORT:-8188}"

# Do NOT start ComfyUI here; rp_handler.py manages it per job.
echo "[startup] Starting RunPod handler..."
exec "$PY" -u rp_handler.py
