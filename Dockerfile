FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# ---- Env ----
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PATH=/root/miniconda3/bin:$PATH

# ---- System deps ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget git ca-certificates \
    ffmpeg libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev libgl1 \
 && rm -rf /var/lib/apt/lists/*

# (Optional) if you plan to git lfs large models:
# RUN apt-get update && apt-get install -y git-lfs && git lfs install && rm -rf /var/lib/apt/lists/*

# ---- Miniconda ----
RUN mkdir -p /root/miniconda3 \
 && wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /root/miniconda3/miniconda.sh \
 && bash /root/miniconda3/miniconda.sh -b -u -p /root/miniconda3 \
 && rm /root/miniconda3/miniconda.sh

# Use bash as shell for the following RUN steps
SHELL ["/bin/bash", "-c"]

# ---- App dir ----
WORKDIR /app

# ---- Clone ComfyUI ----
RUN git clone https://github.com/comfyanonymous/ComfyUI.git

# ---- Create env + install deps ----
RUN source /root/miniconda3/bin/activate \
 && conda create -y -n comfyui python=3.10 \
 && conda run -n comfyui conda install -y -c conda-forge ffmpeg \
 && conda run -n comfyui pip install --no-cache-dir \
      torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 \
 && conda run -n comfyui pip install --no-cache-dir \
      runpod boto3 python-dotenv requests omegaconf einops huggingface_hub

# ---- ComfyUI requirements ----
WORKDIR /app/ComfyUI
RUN conda run -n comfyui pip install --no-cache-dir -r requirements.txt

# ---- Prepare directories (ComfyUI also creates these; harmless to pre-create) ----
RUN mkdir -p /app/ComfyUI/models/checkpoints \
             /app/ComfyUI/models/vae \
             /app/ComfyUI/models/loras \
             /app/ComfyUI/models/embeddings \
             /app/ComfyUI/input \
             /app/ComfyUI/output

# ---- Copy your files ----
COPY rp_handler.py      /app/ComfyUI/rp_handler.py
COPY startup.sh         /app/ComfyUI/startup.sh
COPY workflow_api.json  /app/ComfyUI/workflow_api.json

# ---- Permissions ----
RUN chmod +x /app/ComfyUI/startup.sh

# ---- Runtime ----
WORKDIR /app/ComfyUI
# Pass the env’s Python explicitly to avoid relying on interactive shell activation
ENV COMFY_ENV_PY=/root/miniconda3/envs/comfyui/bin/python
CMD ["/app/ComfyUI/startup.sh"]
