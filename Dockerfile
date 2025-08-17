FROM runpod/worker-comfy:5.2.0-base


RUN ls /
RUN ls /comfyui
RUN rm -f /comfyui/extra_model_paths.yaml
ADD extra_model_paths.yaml /comfyui/extra_model_paths.yaml
