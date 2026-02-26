"""Dataset preparation, response labeling, and text generation helpers."""

import random
import gc
import numpy as np
from datetime import datetime


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_triviaqa_questions(n=40):
    """Load TriviaQA questions with answers."""
    from datasets import load_dataset

    log("Loading TriviaQA dataset...")
    ds = load_dataset("trivia_qa", "rc", split="train", trust_remote_code=True)

    indices = random.sample(range(len(ds)), min(n * 2, len(ds)))
    questions = []
    for i in indices:
        item = ds[i]
        answers = item["answer"]["aliases"]
        if answers and len(answers[0]) < 50:
            questions.append({
                "question": item["question"],
                "answers": [a.lower().strip() for a in answers],
            })
        if len(questions) >= n:
            break

    log(f"Loaded {len(questions)} TriviaQA questions")
    return questions


def generate_and_label(model, tokenizer, questions, config):
    """Generate responses and label as faithful/hallucinated."""
    import torch

    responses_per_q = config.get("responses_per_question", 6)
    max_new_tokens = config.get("max_new_tokens", 30)
    temperature = config.get("temperature", 0.9)
    target_examples = config.get("target_examples", 100)
    chat_template = config.get("chat_template", None)

    faithful = []
    hallucinated = []

    log(f"Generating {responses_per_q} responses per question for {len(questions)} questions...")

    for qi, q in enumerate(questions):
        if len(faithful) >= target_examples // 2 and len(hallucinated) >= target_examples // 2:
            break

        prompt = _format_prompt(q["question"], tokenizer, chat_template)
        input_ids = tokenizer.encode(prompt, return_tensors="pt")
        if config.get("device", "cpu") != "cpu":
            input_ids = input_ids.to(config["device"])
        prompt_len = input_ids.shape[1]

        for _ in range(responses_per_q):
            with torch.no_grad():
                output = model.generate(
                    input_ids,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=True,
                    top_p=0.95,
                    pad_token_id=tokenizer.eos_token_id,
                )

            response_ids = output[0][prompt_len:]
            response_text = tokenizer.decode(response_ids, skip_special_tokens=True).strip()

            is_faithful = any(ans in response_text.lower() for ans in q["answers"])

            entry = {
                "question": q["question"],
                "response": response_text,
                "answers": q["answers"],
                "prompt_ids": input_ids[0].cpu().tolist(),
                "response_ids": response_ids.cpu().tolist(),
                "prompt_len": prompt_len,
            }

            if is_faithful and len(faithful) < target_examples // 2:
                faithful.append(entry)
            elif not is_faithful and len(hallucinated) < target_examples // 2:
                hallucinated.append(entry)

        if (qi + 1) % 10 == 0:
            log(f"  Q {qi+1}/{len(questions)}: {len(faithful)} faithful, {len(hallucinated)} hallucinated")

    log(f"Final: {len(faithful)} faithful, {len(hallucinated)} hallucinated")

    min_count = min(len(faithful), len(hallucinated))
    if min_count == 0:
        log("WARNING: Could not get balanced dataset!")
        return faithful + hallucinated, [0] * len(faithful) + [1] * len(hallucinated)

    faithful = faithful[:min_count]
    hallucinated = hallucinated[:min_count]

    data = faithful + hallucinated
    labels = [0] * len(faithful) + [1] * len(hallucinated)

    combined = list(zip(data, labels))
    random.shuffle(combined)
    data, labels = zip(*combined)

    return list(data), list(labels)


def _format_prompt(question, tokenizer, chat_template=None):
    """Format a question as a chat prompt."""
    if chat_template:
        return chat_template.format(question=question)

    # Try to use the tokenizer's chat template
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            messages = [{"role": "user", "content": question}]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            return prompt
        except Exception:
            pass

    # Fallback for TinyLlama-style
    return f"<|user|>\n{question}\n<|assistant|>\n"


def get_mlp_info(model):
    """Discover MLP layer structure."""
    info = {"layers": [], "total_neurons": 0}

    for name, module in model.named_modules():
        if hasattr(module, 'gate_proj') and hasattr(module, 'up_proj'):
            intermediate_size = module.up_proj.out_features
            info["layers"].append({
                "name": name,
                "module": module,
                "intermediate_size": intermediate_size,
            })
            info["total_neurons"] += intermediate_size

    log(f"Found {len(info['layers'])} MLP layers, {info['total_neurons']:,} total neurons")
    return info
