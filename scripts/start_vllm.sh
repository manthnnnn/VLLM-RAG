#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting Enterprise vLLM Engine"
echo "=========================================================="

# Check GPU availability
if command -v nvidia-smi &> /dev/null; then
    echo "GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "WARNING: nvidia-smi not found. GPU may not be available."
fi

echo "Initializing vLLM model: Qwen/Qwen2.5-7B-Instruct-AWQ"

# Start the vLLM OpenAI-compatible server in the foreground
python3 -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ \
    --quantization awq \
    --gpu-memory-utilization 0.85 \
    --max-model-len 4096 \
    --enable-prefix-caching \
    --port 8000 \
    --host 0.0.0.0
