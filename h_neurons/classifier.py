"""Sparse logistic regression training for H-Neuron identification."""

import numpy as np
from .utils import log


def train_classifier(profiles, labels, mlp_info, C=0.05, test_split=0.2, seed=42):
    """Train L1-regularized logistic regression to find H-Neurons."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score, classification_report

    log("Training sparse logistic regression...")

    X = profiles
    y = np.array(labels)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_split, random_state=seed, stratify=y
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    clf = LogisticRegression(
        penalty='l1',
        solver='saga',
        C=C,
        max_iter=2000,
        random_state=seed,
        verbose=1,
    )
    clf.fit(X_train_s, y_train)

    y_pred = clf.predict(X_test_s)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, output_dict=True)

    log(f"Test accuracy: {accuracy:.4f}")

    weights = clf.coef_[0]
    nonzero_mask = weights != 0
    h_neuron_indices = np.where(nonzero_mask)[0]

    h_neurons = []
    offset = 0
    for li, layer_info in enumerate(mlp_info["layers"]):
        size = layer_info["intermediate_size"]
        for idx in h_neuron_indices:
            if offset <= idx < offset + size:
                h_neurons.append({
                    "global_idx": int(idx),
                    "layer": li,
                    "layer_name": layer_info["name"],
                    "position": int(idx - offset),
                    "weight": float(weights[idx]),
                })
        offset += size

    total = mlp_info["total_neurons"]
    pct = len(h_neurons) / total * 100
    permille = len(h_neurons) / total * 1000

    log(f"H-Neurons found: {len(h_neurons)} / {total:,} ({pct:.4f}%, {permille:.2f}‰)")

    pos_neurons = [n for n in h_neurons if n["weight"] > 0]
    neg_neurons = [n for n in h_neurons if n["weight"] < 0]
    log(f"  Positive weight (hallucination-promoting): {len(pos_neurons)}")
    log(f"  Negative weight (faithfulness-promoting): {len(neg_neurons)}")

    return {
        "clf": clf,
        "scaler": scaler,
        "h_neurons": h_neurons,
        "accuracy": accuracy,
        "report": report,
        "total_neurons": total,
        "X_test": X_test,
        "y_test": y_test,
    }
