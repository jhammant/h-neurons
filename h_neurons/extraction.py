"""CETT metric computation and PyTorch hooks for MLP activation extraction."""

import gc
import numpy as np
import torch
from .utils import log


def extract_activations(model, tokenizer, data, mlp_info, device="cpu"):
    """
    Extract CETT-based neuron activation profiles for each example.

    CETT = |n(x)| / |y| where:
    - n(x) = individual neuron's contribution to the output
    - y = total layer output

    For LLaMA-style MLP: y = down_proj(act(gate_proj(x)) * up_proj(x))
    The "neurons" are the intermediate dimensions.
    """
    num_layers = len(mlp_info["layers"])
    total_neurons = mlp_info["total_neurons"]

    log(f"Extracting activations for {len(data)} examples across {num_layers} layers ({total_neurons:,} neurons)...")

    all_profiles = []

    for di, entry in enumerate(data):
        input_ids = torch.tensor([entry["prompt_ids"] + entry["response_ids"]])
        if device != "cpu":
            input_ids = input_ids.to(device)
        prompt_len = entry["prompt_len"]

        layer_activations = {}
        hooks = []

        def make_hook(layer_idx, mlp_type):
            def hook_fn(module, input, output):
                x = input[0]
                if mlp_type == "gated":
                    gate = module.gate_proj(x)
                    up = module.up_proj(x)
                    intermediate = torch.nn.functional.silu(gate) * up
                else:  # standard MLP (Phi-2, etc.)
                    intermediate = module.activation_fn(module.fc1(x))
                resp_intermediate = intermediate[0, prompt_len:, :]
                resp_output = output[0, prompt_len:, :]

                neuron_magnitude = resp_intermediate.abs().mean(dim=0).float()
                output_norm = resp_output.norm(dim=-1).mean().float()

                if output_norm > 0:
                    cett = neuron_magnitude / output_norm
                else:
                    cett = neuron_magnitude * 0

                layer_activations[layer_idx] = cett.detach().cpu().numpy()
            return hook_fn

        for li, layer_info in enumerate(mlp_info["layers"]):
            h = layer_info["module"].register_forward_hook(make_hook(li, layer_info["mlp_type"]))
            hooks.append(h)

        with torch.no_grad():
            model(input_ids)

        for h in hooks:
            h.remove()

        profile = np.concatenate([layer_activations[li] for li in range(num_layers)])
        all_profiles.append(profile)

        if (di + 1) % 50 == 0:
            log(f"  Extracted {di+1}/{len(data)} profiles")

        del input_ids, layer_activations
        if (di + 1) % 100 == 0:
            gc.collect()

    profiles = np.array(all_profiles)
    log(f"Activation matrix shape: {profiles.shape}")
    return profiles
