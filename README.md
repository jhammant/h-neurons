# H-Neurons: Find and Disable Hallucination Neurons in LLMs

Reproduction and extension of ["H-Neurons: On the Existence, Impact, and Origin of Hallucination-Associated Neurons in LLMs"](https://arxiv.org/abs/2512.01797) (Gao et al., 2025).

**TL;DR:** Less than 0.1% of neurons in an LLM are responsible for hallucinations. This tool finds them and lets you turn them off.

## Quick Start (Mac M4)

```bash
git clone https://github.com/jhammant/h-neurons
cd h-neurons
bash scripts/run_mac.sh
```

## What It Does

1. **Identifies H-Neurons** — Uses TriviaQA to generate faithful/hallucinated responses, extracts neuron activations via CETT metric, trains sparse logistic regression to find the ~30 neurons most predictive of hallucination

2. **Suppresses H-Neurons** — Zeros out identified neurons during inference and tests if hallucination rate drops

3. **Amplifies H-Neurons** — Doubles neuron activations to confirm hallucination increases (control experiment)

## Results

### TinyLlama-1.1B (ARM64 CPU, our test)
- **31 H-Neurons** found (0.025% of 123,904)
- 60% detection accuracy
- Intervention inconclusive (model too small)

### Expected on Llama-3.1-8B (Mac M4)
- Paper reports 0.02‰ neurons, 70.1% detection accuracy
- Suppression expected to reduce hallucination rate
- Amplification expected to increase sycophancy

## Models Tested in Original Paper

| Model | H-Neurons (‰) | Accuracy |
|-------|---------------|----------|
| Mistral-7B-v0.3 | 0.35 | 78.4% |
| Gemma-3-4B | 0.10 | 76.9% |
| Llama-3.1-8B | 0.02 | 70.1% |
| Llama-3.3-70B | 0.01 | 82.7% |

## Usage

```bash
# Full pipeline with config file
python scripts/run_full.py --config configs/llama8b.json

# Just identification
python scripts/run_full.py --config configs/llama8b.json --phase identify

# Just intervention (using saved neurons)
python scripts/run_full.py --config configs/llama8b.json --phase intervene --neurons results/llama8b/h_neurons.json

# CLI args (no config file)
python scripts/run_full.py --model meta-llama/Llama-3.1-8B-Instruct --quantize 4bit --samples 200 --responses-per-question 8
```

### Arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `--config` | — | JSON config file |
| `--model` | TinyLlama-1.1B | HuggingFace model name |
| `--quantize` | none | none/4bit/8bit (4bit/8bit need CUDA) |
| `--samples` | 40 | TriviaQA questions |
| `--responses-per-question` | 6 | Responses per question |
| `--output` | results | Output directory |
| `--device` | auto | auto/cpu/cuda/mps |
| `--phase` | full | full/identify/intervene |
| `--neurons` | — | Path to saved h_neurons.json |

## How It Works

### CETT Metric

For each neuron `n` in MLP layer `l`:

```
CETT(n, x) = |n(x)| / |y_l|
```

Where `n(x)` is the neuron's intermediate activation magnitude and `y_l` is the layer output norm. This measures each neuron's relative contribution to the output.

### Pipeline

1. **Generate**: Sample TriviaQA questions, generate multiple responses at high temperature
2. **Label**: Responses containing the correct answer → faithful; otherwise → hallucinated
3. **Extract**: Compute CETT profiles across all MLP layers for each response
4. **Classify**: Train L1-regularized logistic regression — non-zero weights = H-Neurons
5. **Intervene**: Zero out (suppress) or amplify H-Neuron activations during inference

### Device Support

- **CPU**: Works everywhere, slow on large models
- **MPS (Apple Silicon)**: fp16, good for models up to ~8B
- **CUDA**: fp16 + 4bit/8bit quantization via bitsandbytes

Note: bitsandbytes quantization only works on CUDA. On MPS/CPU, models load in fp16.

## Project Structure

```
h-neurons/
├── h_neurons/           # Core library
│   ├── experiment.py    # Main pipeline orchestrator
│   ├── extraction.py    # CETT metric + activation hooks
│   ├── classifier.py    # Sparse logistic regression
│   ├── intervention.py  # Neuron suppression/amplification
│   └── utils.py         # Dataset loading, helpers
├── scripts/             # CLI entry points
│   ├── run_full.py      # Full pipeline
│   ├── run_identify.py  # Identification only
│   ├── run_intervene.py # Intervention only
│   └── run_mac.sh       # Mac one-liner setup
├── configs/             # Model configs
│   ├── tinyllama.json
│   ├── llama8b.json
│   ├── phi2.json
│   └── mistral7b.json
└── results/             # Experiment results
    └── tinyllama-1.1b/  # Our ARM results
```

## Citation

If you use this in research:

```bibtex
@article{gao2025hneurons,
  title={H-Neurons: On the Existence, Impact, and Origin of Hallucination-Associated Neurons in LLMs},
  author={Gao, Cheng and Chen, Huimin and Xiao, Chaojun and Chen, Zhiyi and Liu, Zhiyuan and Sun, Maosong},
  journal={arXiv preprint arXiv:2512.01797},
  year={2025}
}
```

## License

MIT
