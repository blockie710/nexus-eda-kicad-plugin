---
title: "AI Engines"
weight: 40
---

# AI Engines

The Nexus-EDA LLM engine is configured via `models/manifest.yaml` and loaded
through the `nexus_eda.llm.engine` module.

## Model Configuration

All model parameters are read from [`models/manifest.yaml`](https://github.com/blockie710/nexus-eda-kicad-plugin/blob/master/models/manifest.yaml)
at runtime. The engine reads the `runtime` section for defaults and the primary
model entry.

### Runtime Defaults

| Parameter      | Value       | Description                        |
|----------------|-------------|------------------------------------|
| `backend`      | `llama-cpp-python` | Inference runtime              |
| `api_url`      | `http://localhost:8000` | HTTP fallback endpoint    |
| `quantization` | `Q4_K_M`    | 4-bit quantization                 |
| `temperature`  | `0.1`       | Low for deterministic reasoning    |
| `top_p`        | `0.9`       | Nucleus sampling                   |
| `max_tokens`   | `4096`      | Max output per request             |

### Environment Variables

| Variable              | Description                                      |
|-----------------------|--------------------------------------------------|
| `NEXUS_LLM_MODEL_PATH`| Path to the `.gguf` model file on disk          |
| `NEXUS_LLM_API_URL`   | Override the HTTP API endpoint (server mode)    |

## Loading a Model

```python
from nexus_eda.llm.engine import load_model, generate

# Load the primary model from the manifest
engine = load_model()

# Or specify a custom path
engine = load_model(model_path="models/my-model-Q4_K_M.gguf")

# Generate a response
response = engine.generate("What are the best practices for PCB routing?")

# Stream tokens
for token in engine.generate_stream("Explain differential pairs."):
    print(token, end="", flush=True)
```

## Using the HTTP Server (No Direct GPU Access)

If you run `llama-cpp-python` as a server, the engine falls back to HTTP:

```bash
# Start the server
python -m llama_cpp.server \
  --model models/DeepSeek-V3-0324-Q4_K_M.gguf \
  --port 8000 \
  --n-gpu-layers -1
```

The engine will automatically use the HTTP endpoint if the in-process binding
is unavailable.

## Model Recommendations

| Use Case          | Recommended Model           | VRAM |
|-------------------|-------------------------------|------|
| General agents    | DeepSeek-V3-0324 (8B, Q4)    | 6-8 GB |
| Fast/lightweight  | Qwen2.5-7B (Q4)              | 5-6 GB |
| Vision (Phase 1.5+) | Qwen2.5-VL-7B               | 8-10 GB |
| Fallback          | Llama-3.1-8B (Q4)            | 7 GB |
