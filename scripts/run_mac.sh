#!/bin/bash
# One-liner setup for Mac M4 (Apple Silicon)
set -e

echo "🧠 H-Neurons Experiment — Mac Setup"

# Create venv if needed
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install deps (MPS-compatible torch)
pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -q transformers datasets scikit-learn numpy bitsandbytes accelerate

# Run with Llama-3.1-8B on MPS
echo "🚀 Running H-Neurons identification + intervention..."
python scripts/run_full.py --config configs/llama8b.json

echo "✅ Done! Results in results/"
