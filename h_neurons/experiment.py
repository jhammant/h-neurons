"""Main experiment runner — orchestrates the full H-Neurons pipeline."""

import json
import gc
import time
import random
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from .utils import log, load_triviaqa_questions, generate_and_label, get_mlp_info, _format_prompt
from .extraction import extract_activations
from .classifier import train_classifier
from .intervention import run_intervention_tests


class HNeuronsExperiment:
    """Class-based wrapper for the H-Neurons experiment pipeline."""

    def __init__(self, model_name="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
                 quantize="none", device="auto", samples=100,
                 responses_per_question=6, **kwargs):
        self.config = {
            "model": model_name,
            "quantize": quantize,
            "device": device,
            "samples": samples,
            "responses_per_question": responses_per_question,
            **kwargs,
        }
        self.model = None
        self.tokenizer = None
        self.mlp_info = None
        self.data = None
        self.labels = None
        self._profiles = None
        self.total_neurons = 0

    def load_model(self):
        self.model, self.tokenizer = load_model(self.config)
        self.mlp_info = get_mlp_info(self.model)
        self.total_neurons = self.mlp_info["total_neurons"]

    def generate_dataset(self):
        questions = load_triviaqa_questions(self.config["samples"])
        self.data, self.labels = generate_and_label(
            self.model, self.tokenizer, questions, self.config
        )

    def extract_activations(self):
        self._profiles = extract_activations(
            self.model, self.tokenizer, self.data, self.mlp_info,
            device=self.config.get("device", "cpu")
        )

    def train_classifier(self):
        results = train_classifier(
            self._profiles, self.labels, self.mlp_info,
            C=self.config.get("classifier_C", 0.05),
        )
        self._classifier_results = results
        h_neuron_indices = [(n["layer"], n["position"]) for n in results["h_neurons"]]
        self.total_neurons = results["total_neurons"]
        return h_neuron_indices, results["accuracy"]

    def generate_with_intervention(self, question, h_neuron_indices, scale=1.0):
        """Generate a response with H-Neurons scaled by the given factor.

        scale=1.0: original (no intervention)
        scale=0.0: suppressed (truthful)
        scale>1.0: amplified (creative)
        """
        import torch

        prompt = _format_prompt(question, self.tokenizer)
        input_ids = self.tokenizer.encode(prompt, return_tensors="pt")
        device = self.config.get("device", "cpu")
        if device != "cpu":
            input_ids = input_ids.to(device)

        hooks = []
        if scale != 1.0:
            layer_neurons = defaultdict(list)
            for layer, position in h_neuron_indices:
                layer_neurons[layer].append(position)

            import torch as _torch

            def make_hook(positions, scale, mlp_type):
                positions_tensor = None

                def hook_fn(module, input, output):
                    nonlocal positions_tensor
                    x = input[0]
                    if mlp_type == "gated":
                        gate = module.gate_proj(x)
                        up = module.up_proj(x)
                        intermediate = _torch.nn.functional.silu(gate) * up
                    else:  # standard MLP
                        intermediate = module.activation_fn(module.fc1(x))
                    if positions_tensor is None:
                        positions_tensor = _torch.tensor(
                            positions, dtype=_torch.long,
                            device=intermediate.device
                        )
                    intermediate[:, :, positions_tensor] *= scale
                    if mlp_type == "gated":
                        return module.down_proj(intermediate)
                    else:
                        return module.fc2(intermediate)

                return hook_fn

            for li, positions in layer_neurons.items():
                if positions:
                    layer_info = self.mlp_info["layers"][li]
                    h = layer_info["module"].register_forward_hook(
                        make_hook(positions, scale, layer_info["mlp_type"])
                    )
                    hooks.append(h)

        with torch.no_grad():
            output = self.model.generate(
                input_ids,
                max_new_tokens=self.config.get("max_new_tokens", 150),
                temperature=0.1,
                do_sample=True,
                top_p=0.95,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        for h in hooks:
            h.remove()

        response = self.tokenizer.decode(
            output[0][input_ids.shape[1]:], skip_special_tokens=True
        ).strip()
        return response


def load_model(config):
    """Load model with optional quantization."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_name = config["model"]
    device = config.get("device", "auto")
    quantize = config.get("quantize", "none")

    log(f"Loading {model_name} (quantize={quantize}, device={device})...")

    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Phi-2 is natively supported; trust_remote_code can cause issues
    # with custom_generate downloads on flaky networks
    needs_remote_code = "phi-2" not in model_name.lower()

    load_kwargs = {
        "trust_remote_code": needs_remote_code,
        "low_cpu_mem_usage": True,
    }

    # Determine device
    if device == "auto":
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        config["device"] = device
        log(f"Auto-detected device: {device}")

    # Quantization (bitsandbytes — CUDA only)
    if quantize in ("4bit", "8bit") and device == "cuda":
        try:
            from transformers import BitsAndBytesConfig
            if quantize == "4bit":
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                )
            else:
                load_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_8bit=True)
            load_kwargs["device_map"] = "auto"
            log(f"Using {quantize} quantization (bitsandbytes)")
        except ImportError:
            log("WARNING: bitsandbytes not available, falling back to fp16")
            quantize = "none"
    elif quantize in ("4bit", "8bit") and device != "cuda":
        log(f"WARNING: {quantize} quantization requires CUDA. Using fp16 on {device}.")
        quantize = "none"

    if quantize == "none":
        load_kwargs["torch_dtype"] = torch.float16
        if device == "cpu":
            load_kwargs["device_map"] = "cpu"
        elif device == "mps":
            load_kwargs["device_map"] = "mps"
        else:
            load_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(model_name, **load_kwargs)
    model.eval()

    param_count = sum(p.numel() for p in model.parameters())
    log(f"Model loaded. Parameters: {param_count:,}")

    return model, tokenizer


def run_experiment(config):
    """Run the full H-Neurons experiment pipeline."""
    seed = config.get("seed", 42)
    random.seed(seed)
    np.random.seed(seed)

    timing = {}
    t_start = time.time()

    # Phase 0: Load model
    t0 = time.time()
    model, tokenizer = load_model(config)
    mlp_info = get_mlp_info(model)
    timing["model_load"] = time.time() - t0

    phase = config.get("phase", "full")

    if phase in ("full", "identify"):
        # Phase 1a: Create dataset
        t0 = time.time()
        questions = load_triviaqa_questions(config.get("samples", 40))
        data, labels = generate_and_label(model, tokenizer, questions, config)
        timing["dataset"] = time.time() - t0

        if len(data) < 20:
            log("ERROR: Not enough data generated. Aborting.")
            return None

        log(f"Dataset: {len(data)} examples, {sum(1 for l in labels if l==0)} faithful, {sum(1 for l in labels if l==1)} hallucinated")

        # Phase 1b: Extract activations
        t0 = time.time()
        profiles = extract_activations(model, tokenizer, data, mlp_info, device=config.get("device", "cpu"))
        timing["extraction"] = time.time() - t0

        # Phase 1c: Train classifier
        t0 = time.time()
        classifier_results = train_classifier(
            profiles, labels, mlp_info,
            C=config.get("classifier_C", 0.05),
            seed=seed,
        )
        timing["classifier"] = time.time() - t0

        h_neurons = classifier_results["h_neurons"]

        del profiles
        gc.collect()

        # Save h_neurons
        output_dir = Path(config.get("output", "results"))
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / "h_neurons.json", "w") as f:
            json.dump(h_neurons, f, indent=2)
        log(f"Saved {len(h_neurons)} H-Neurons to {output_dir / 'h_neurons.json'}")

    elif phase == "intervene":
        # Load saved neurons
        neurons_path = config.get("neurons")
        if not neurons_path:
            log("ERROR: --neurons path required for intervene phase")
            return None
        with open(neurons_path) as f:
            h_neurons = json.load(f)
        classifier_results = {"h_neurons": h_neurons, "total_neurons": mlp_info["total_neurons"]}
        data = []
        labels = []
        log(f"Loaded {len(h_neurons)} H-Neurons from {neurons_path}")

    # Phase 2: Intervention tests
    if phase in ("full", "intervene"):
        t0 = time.time()
        if len(h_neurons) == 0:
            log("WARNING: No H-Neurons found! Skipping intervention tests.")
            intervention_results = {}
        else:
            intervention_results = run_intervention_tests(model, tokenizer, mlp_info, h_neurons, config)
        timing["intervention"] = time.time() - t0
    else:
        intervention_results = {}

    timing["total"] = time.time() - t_start

    # Save results
    output_dir = Path(config.get("output", "results"))
    output_dir.mkdir(parents=True, exist_ok=True)

    results_json = {
        "model": config["model"],
        "timestamp": datetime.now().isoformat(),
        "timing": timing,
        "h_neurons": classifier_results.get("h_neurons", []),
        "total_neurons": classifier_results.get("total_neurons", 0),
        "detection_accuracy": classifier_results.get("accuracy"),
        "classification_report": classifier_results.get("report"),
        "num_examples": len(data) if data else 0,
        "intervention_results": intervention_results,
        "config": {k: v for k, v in config.items() if k != "device" or isinstance(v, str)},
    }

    with open(output_dir / "results.json", "w") as f:
        json.dump(results_json, f, indent=2, default=str)

    log(f"\nResults saved to {output_dir}")
    log(f"Total runtime: {timing['total']:.0f}s")

    return results_json
