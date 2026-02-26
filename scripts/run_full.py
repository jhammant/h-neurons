#!/usr/bin/env python3
"""Full H-Neurons pipeline: identify hallucination neurons + intervention tests."""

import argparse
import json
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from h_neurons.experiment import run_experiment


def main():
    parser = argparse.ArgumentParser(
        description="H-Neurons: Find and disable hallucination neurons in LLMs"
    )
    parser.add_argument("--config", type=str, help="Path to JSON config file")
    parser.add_argument("--model", type=str, default="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                        help="HuggingFace model name")
    parser.add_argument("--quantize", choices=["none", "4bit", "8bit"], default="none",
                        help="Quantization mode (4bit/8bit require CUDA + bitsandbytes)")
    parser.add_argument("--samples", type=int, default=40,
                        help="Number of TriviaQA questions to sample")
    parser.add_argument("--responses-per-question", type=int, default=6,
                        help="Responses to generate per question")
    parser.add_argument("--output", type=str, default="results",
                        help="Output directory for results")
    parser.add_argument("--device", type=str, default="auto",
                        choices=["auto", "cpu", "cuda", "mps"],
                        help="Device to run on")
    parser.add_argument("--phase", type=str, default="full",
                        choices=["full", "identify", "intervene"],
                        help="Which phase to run")
    parser.add_argument("--neurons", type=str,
                        help="Path to saved h_neurons.json (for --phase intervene)")
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--max-new-tokens", type=int, default=100)
    parser.add_argument("--classifier-C", type=float, default=0.05,
                        help="Inverse L1 regularization strength")
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    # Build config from file + CLI overrides
    config = {}
    if args.config:
        with open(args.config) as f:
            config = json.load(f)

    # CLI args override config file
    cli_overrides = {
        "model": args.model,
        "quantize": args.quantize,
        "samples": args.samples,
        "responses_per_question": args.responses_per_question,
        "output": args.output,
        "device": args.device,
        "phase": args.phase,
        "neurons": args.neurons,
        "temperature": args.temperature,
        "max_new_tokens": args.max_new_tokens,
        "classifier_C": args.classifier_C,
        "seed": args.seed,
    }

    # Only override if not using config file, or if explicitly set on CLI
    if args.config:
        # Config file values are defaults; explicit CLI args override
        for k, v in cli_overrides.items():
            if k not in config:
                config[k] = v
    else:
        config = cli_overrides

    run_experiment(config)


if __name__ == "__main__":
    main()
