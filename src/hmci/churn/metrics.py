"""Metrics shared by every churn model."""
from __future__ import annotations

import numpy as np
import polars as pl
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

def lift_at(y: np.ndarray, score: np.ndarray, frac: float = 0.10) -> float:
    """Churn rate among the top `frac` highest scores, divided by the overall churn rate."""
    n = max(1, int(len(y) * frac))
    top = np.argsort(-score)[:n]
    return float(y[top].mean() / y.mean())


def evaluate(name: str, y: np.ndarray, score: np.ndarray, is_prob: bool = True) -> dict:
    out = {
        "model": name,
        "pr_auc": average_precision_score(y, score),
        "roc_auc": roc_auc_score(y, score),
        "lift_top10": lift_at(y, score),
    }
    if is_prob:  # log-loss and Brier only make sense for probabilities
        out |= {"log_loss": log_loss(y, score), "brier": brier_score_loss(y, score)}
    return out


def write_markdown(table: pl.DataFrame, path, title: str) -> None:
    cols = table.columns
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in table.iter_rows():
        lines.append("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
    path.write_text(f"# {title}\n\n" + "\n".join(lines) + "\n")