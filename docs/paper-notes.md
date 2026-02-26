# Paper Notes: H-Neurons

**Paper:** [H-Neurons: On the Existence, Impact, and Origin of Hallucination-Associated Neurons in LLMs](https://arxiv.org/abs/2512.01797)  
**Authors:** Gao, Chen, Xiao, Chen, Liu, Sun (Tsinghua University)  
**Published:** December 2025

## Key Findings

1. **H-Neurons exist**: A tiny fraction (<0.1%) of neurons in LLMs are strongly associated with hallucination behavior
2. **They're detectable**: Using CETT (Contribution to Expected Token Truthfulness) metric + sparse logistic regression
3. **They're actionable**: Suppressing H-Neurons reduces hallucination; amplifying them increases sycophancy

## Method

### CETT Metric
For each neuron `n` in MLP layer `l`, compute:
```
CETT(n, x) = |n(x)| / |y_l|
```
Where `n(x)` is the neuron's activation and `y_l` is the total layer output norm. This measures each neuron's relative contribution.

### Pipeline
1. Generate multiple responses per TriviaQA question at high temperature
2. Label responses as faithful (contains correct answer) or hallucinated
3. Extract CETT profiles for all response tokens across all MLP layers
4. Train L1-regularized logistic regression (very sparse) to classify faithful vs hallucinated
5. Non-zero weights identify H-Neurons

### Intervention
- **Suppress**: Zero out H-Neuron activations during inference → hallucination rate drops
- **Amplify**: Double H-Neuron activations → model becomes more sycophantic/confabulating

## Results from Paper

| Model | Total Neurons | H-Neurons | ‰ | Detection Acc |
|-------|--------------|-----------|-----|---------------|
| Mistral-7B-v0.3 | ~1M | ~350 | 0.35 | 78.4% |
| Gemma-3-4B | ~700K | ~70 | 0.10 | 76.9% |
| Llama-3.1-8B | ~1.1M | ~22 | 0.02 | 70.1% |
| Llama-3.3-70B | ~2.6M | ~26 | 0.01 | 82.7% |

## Key Insight
H-Neurons are concentrated in middle-to-late MLP layers. They correlate with the model's "confidence calibration" — when these neurons fire strongly, the model tends to generate text regardless of factual grounding.
