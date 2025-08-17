import os
import runpod
import subprocess
import uuid
import logging
import shutil
import requests
import json
import time
from dotenv import load_dotenv

# --------------------------------------------
# Setup
# --------------------------------------------
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ComfyUI project root (this file should live in the repo root)
COMFYUI_DIR = os.path.dirname(os.path.abspath(__file__))

# RunPod volume paths (Network Storage)
RUNPOD_VOLUME_PATH = "/workspace"
MODEL_DIR = os.path.join(RUNPOD_VOLUME_PATH, "comfyui", "models")
TEMP_DIR = os.path.join(RUNPOD_VOLUME_PATH, "comfyui", "temp")
OUTPUT_DIR = os.path.join(RUNPOD_VOLUME_PATH, "comfyui", "output")

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

COMFY_PORT = int(os.getenv("COMFY_PORT", "8188"))
COMFY_BASE = f"http://localhost:{COMFY_PORT}"

# Only use CPU if explicitly requested
USE_CPU = os.getenv("USE_CPU", "false").lower() == "true"


# --------------------------------------------
# Helpers
# --------------------------------------------
def _deep_copy(obj):
    """JSON roundtrip deep copy to avoid mutating the base workflow."""
    return json.loads(json.dumps(obj))


def _ensure_models_symlink():
    """
    Ensure ComfyUI's ./models points to the network storage MODEL_DIR so that
    CheckpointLoaderSimple can find files like models/checkpoints/<ckpt>.safetensors
    """
    repo_models = os.path.join(COMFYUI_DIR, "models")

    # Make sure network storage exists
    os.makedirs(MODEL_DIR, exist_ok=True)

    # If repo_models already a correct symlink, done
    if os.path.islink(repo_models) and os.readlink(repo_models) == MODEL_DIR:
        return

    # If it's a real dir
    if os.path.isdir(repo_models) and not os.path.islink(repo_models):
        # If empty, replace with symlink
        if not os.listdir(repo_models):
            shutil.rmtree(repo_models)
        else:
            # Keep user's content; don't replace a non-empty models dir
            logger.warning("Found non-empty ./models directory; not replacing with symlink.")
            return

    # Create symlink if possible
    if os.path.exists(repo_models) and not os.path.islink(repo_models):
        logger.warning("Cannot create models symlink; path exists and is not a symlink.")
        return

    try:
        os.symlink(MODEL_DIR, repo_models)
        logger.info(f"Symlinked {repo_models} -> {MODEL_DIR}")
    except FileExistsError:
        pass


def _wait_for_server(timeout=180):
    """Poll ComfyUI until it responds or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{COMFY_BASE}/system_stats", timeout=2)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(2)
    return False


def load_workflow(workflow_path):
    """Load the ComfyUI workflow from JSON file."""
    try:
        with open(workflow_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading workflow: {e}")
        return None


def modify_workflow(base_workflow, input_params):
    """
    Modify the workflow using actual graph wiring rather than node titles.
    - Sets positive/negative prompts on the CLIPTextEncode nodes wired into KSampler.
    - Updates KSampler controls: seed, steps, cfg, denoise.
    - Updates EmptyLatentImage: width, height.
    - Optionally overrides checkpoint via 'ckpt_name' in input.
    """
    wf = _deep_copy(base_workflow)

    # Optionally override ckpt
    if "ckpt_name" in input_params:
        for node in wf.values():
            if node.get("class_type") == "CheckpointLoaderSimple":
                node.setdefault("inputs", {})["ckpt_name"] = input_params["ckpt_name"]

    # Get first KSampler to discover positive/negative node ids
    ks_id = None
    for node_id, node in wf.items():
        if node.get("class_type") == "KSampler":
            ks_id = node_id
            break

    pos_id = neg_id = None
    if ks_id:
        ks = wf[ks_id]
        if "positive" in ks.get("inputs", {}):
            pos = ks["inputs"]["positive"]
            if isinstance(pos, list) and len(pos) >= 1:
                pos_id = str(pos[0])
        if "negative" in ks.get("inputs", {}):
            neg = ks["inputs"]["negative"]
            if isinstance(neg, list) and len(neg) >= 1:
                neg_id = str(neg[0])

    # Update prompts by node id
    if "positive" in input_params and pos_id and pos_id in wf:
        node = wf[pos_id]
        if node.get("class_type") == "CLIPTextEncode":
            node.setdefault("inputs", {})["text"] = input_params["positive"]

    if "negative" in input_params and neg_id and neg_id in wf:
        node = wf[neg_id]
        if node.get("class_type") == "CLIPTextEncode":
            node.setdefault("inputs", {})["text"] = input_params["negative"]

    # Update KSampler scalars
    for node in wf.values():
        if node.get("class_type") == "KSampler":
            ins = node.setdefault("inputs", {})
            for k in ("seed", "steps", "cfg", "denoise"):
                if k in input_params:
                    ins[k] = input_params[k]

    # Update image size
    for node in wf.values():
        if node.get("class_type") == "EmptyLatentImage":
            ins = node.setdefault("inputs", {})
            if "width" in input_params:
                ins["width"] = input_params["width"]
            if "height" in input_params:
                ins["height"] = input_params["height"]

    return wf


def _start_comfyui(output_dir, tmp_dir):
    """Launch ComfyUI server (headless)."""
    cmd = [
        "python", "main.py",
        "--listen", "0.0.0.0",
        "--port", str(COMFY_PORT),
        "--output-directory", output_dir,
        "--temp-directory", tmp_dir,
    ]
    if USE_CPU:
        cmd.append("--cpu")

    logger.info(f"Starting ComfyUI: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd,
        cwd=COMFYUI_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return process


def _safe_terminate(proc: subprocess.Popen, timeout=10):
    """Terminate the ComfyUI process cleanly."""
    if proc is None:
        return
    try:
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
    except Exception:
        pass


def run_comfyui_workflow(workflow, output_dir):
    """
    Start ComfyUI, send workflow via API, wait until it finishes, collect outputs.
    Returns list of file paths (or empty list on failure).
    """
    wf_file = None
    proc = None
    try:
        _ensure_models_symlink()

        # Persist modified workflow to a temp file (useful for debugging)
        wf_file = os.path.join(TEMP_DIR, f"workflow_{uuid.uuid4()}.json")
        with open(wf_file, "w") as f:
            json.dump(workflow, f, indent=2)

        proc = _start_comfyui(output_dir, TEMP_DIR)

        if not _wait_for_server(timeout=180):
            raise RuntimeError("ComfyUI server did not become ready in time")

        # POST the prompt
        payload = {"prompt": workflow, "client_id": "runpod_handler"}
        r = requests.post(f"{COMFY_BASE}/prompt", json=payload, timeout=30)
        r.raise_for_status()
        prompt_id = r.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return a prompt_id")

        # Poll history for completion
        while True:
            time.sleep(2)
            try:
                hist = requests.get(f"{COMFY_BASE}/history/{prompt_id}", timeout=10)
                if hist.status_code == 200:
                    data = hist.json()
                    if prompt_id in data:
                        break
            except requests.RequestException:
                pass

        # Gather outputs
        outs = []
        for fn in os.listdir(output_dir):
            if fn.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                outs.append(os.path.join(output_dir, fn))
        return outs

    except Exception as e:
        logger.exception(f"Error running ComfyUI workflow: {e}")
        return []
    finally:
        _safe_terminate(proc)
        if wf_file:
            try:
                os.remove(wf_file)
            except OSError:
                pass


# --------------------------------------------
# RunPod handler
# --------------------------------------------
def handler(job):
    """
    RunPod Serverless entry point.
    Input example:
    {
      "positive": "blue fox",
      "negative": "low quality, blurry",
      "seed": 162,
      "steps": 4,
      "cfg": 3,
      "denoise": 0.8,
      "width": 512,
      "height": 512,
      "ckpt_name": "cyberrealistic_v40.safetensors"
    }
    """
    try:
        job_id = str(job.get("id", uuid.uuid4()))
        input_data = job.get("input", {}) or {}
        logger.info(f"Received job {job_id} with input: {input_data}")

        # Load base workflow
        workflow_path = os.path.join(COMFYUI_DIR, "workflow_api.json")
        base_workflow = load_workflow(workflow_path)
        if not base_workflow:
            return {"error": "Failed to load workflow_api.json", "job_id": job_id}

        # Apply overrides
        modified_workflow = modify_workflow(base_workflow, input_data)

        # Per-job output directory on network storage
        job_output_dir = os.path.join(OUTPUT_DIR, job_id)
        os.makedirs(job_output_dir, exist_ok=True)

        # Run workflow
        output_images = run_comfyui_workflow(modified_workflow, job_output_dir)
        if not output_images:
            return {"error": "No images generated", "job_id": job_id}

        # Return absolute file paths on /runpod-volume
        return {
            "job_id": job_id,
            "output_images": output_images
        }

    except Exception as e:
        logger.exception(f"Handler error: {e}")
        return {"error": str(e), "job_id": job.get("id") if isinstance(job, dict) else None}


# --------------------------------------------
# Serverless start
# --------------------------------------------
if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
