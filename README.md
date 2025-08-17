# ComfyUI Workflow for RunPod

This directory contains the implementation of a ComfyUI workflow as a RunPod serverless API endpoint.

## What is ComfyUI?

ComfyUI is a powerful node-based UI for Stable Diffusion. It allows you to create complex image generation workflows by connecting different nodes together.

## API Usage

### Input Format

```json
{
  "input": {
    "positive": "your positive prompt here",
    "negative": "your negative prompt here",
    "seed": 42,
    "steps": 20,
    "cfg": 7.0,
    "denoise": 1.0,
    "width": 512,
    "height": 512
  }
}
```

### Output Format

```json
{
  "output_images": [
    "https://your-bucket.s3.region.amazonaws.com/comfyui/outputs/job_id/image.png"
  ],
  "job_id": "job_id"
}
```

### Input Parameters

- **positive**: Text prompt describing what you want to generate
- **negative**: Text prompt describing what you don't want to generate
- **seed**: Random seed for reproducible results (optional)
- **steps**: Number of denoising steps (optional, default: 20)
- **cfg**: Classifier-free guidance scale (optional, default: 7.0)
- **denoise**: Denoising strength (optional, default: 1.0)
- **width**: Image width in pixels (optional, default: 512)
- **height**: Image height in pixels (optional, default: 512)

## Environment Variables

**S3 Configuration (Optional)**
Create a `.env` file with the following variables if you want to store images in S3:

```
S3_ACCESS_KEY=your_s3_access_key
S3_SECRET_KEY=your_s3_secret_key
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=your_bucket_name
S3_REGION=us-east-1
```

## Running Locally

To run the container locally:

### With S3 (for image storage):
```bash
docker build -t comfyui-runpod .
docker run -p 8000:8000 \
  -v /path/to/local/volume:/runpod-volume \
  -e S3_ACCESS_KEY=your_s3_access_key \
  -e S3_SECRET_KEY=your_s3_secret_key \
  -e S3_BUCKET=your_bucket_name \
  -e S3_REGION=your_region \
  comfyui-runpod
```

### Without S3 (images stored locally):
```bash
docker build -t comfyui-runpod .
docker run -p 8000:8000 \
  -v /path/to/local/volume:/runpod-volume \
  comfyui-runpod
```

## Testing

After starting the container, you can test it with:

```bash
curl -X POST "http://localhost:8000/run" \
  -H "Content-Type: application/json" \
  -d @test_input.json
```

## RunPod Setup

1. **Create a Template**:
   - Build the Docker image and push to a registry
   - Create a RunPod template using the Docker image

2. **Set up Environment Variables** (optional):
   - Add S3 credentials if you want to store outputs in S3
   - **Note**: S3 is completely optional - see `NOS3_SETUP_GUIDE.md` for details

3. **Create a Serverless Endpoint**:
   - Use the template to create a serverless endpoint
   - Attach a RunPod volume to persist models

4. **Model Setup** (Recommended):
   - Upload your models to a RunPod volume (see `UPLOAD_MODELS_GUIDE.md`)
   - Attach the volume to your endpoint with mount path `/runpod-volume`
   - Models will be automatically loaded from the volume

## Model Requirements

The workflow requires the following models:

- **Checkpoint**: `cyberrealistic_v40.safetensors` (or modify the workflow to use your preferred model)
- **VAE**: Usually included with the checkpoint
- **Additional models**: Any LoRAs, embeddings, or other models referenced in your workflow

**📁 Recommended Setup**: Upload models to RunPod volume (see `UPLOAD_MODELS_GUIDE.md`)

**🚫 No S3 Setup**: See `NOS3_SETUP_GUIDE.md` for deployment without S3 storage

## How It Works

1. The handler loads the base workflow from `workflow_api.json`
2. Modifies the workflow with input parameters (prompts, settings, etc.)
3. Runs ComfyUI in headless mode with the modified workflow
4. Waits for completion and collects generated images
5. Uploads results to S3 (if configured) or returns local paths
6. Returns the image URLs

## Customizing the Workflow

To modify the workflow:

1. Edit `workflow_api.json` to change the node structure
2. Update the `modify_workflow()` function in `rp_handler.py` to handle new parameters
3. Add any required models to the startup script

## Troubleshooting

- **Model not found**: Ensure your models are uploaded to the RunPod volume (see `UPLOAD_MODELS_GUIDE.md`)
- **CUDA errors**: The container uses CPU by default. For GPU support, modify the Dockerfile and handler
- **Memory issues**: Adjust the image dimensions or batch size in your workflow
- **Volume issues**: Check that the volume is properly attached with mount path `/runpod-volume`

## Credits

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [RunPod](https://runpod.io) 