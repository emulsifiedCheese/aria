"""phase 11.3 development ablation table and figure"""
from __future__ import annotations
import os
from pathlib import Path
import tempfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from aria.modeling.baselines import CLASS_LABELS, _load_json, _write_text_atomic

MODEL_ORDER = (
    "camera_only",
    "camera_a1",
    "camera_a2",
    "camera_a1_a2",
    "a1_a2",
    "a1_only",
    "majority",
)
MODEL_LABELS = {
    "camera_only": "Camera A only",
    "camera_a1": "Camera A + ESP-A1",
    "camera_a2": "Camera A + ESP-A2",
    "camera_a1_a2": "Camera A + ESP-A1 + ESP-A2",
    "a1_a2": "ESP-A1 + ESP-A2",
    "a1_only": "ESP-A1 only",
    "majority": "Majority",
}

class AblationError(ValueError):
    """raised when frozen ablation evidence is incomplete"""

def _validate(report: dict) -> dict:
    if (
        report.get("phase") != "11.3"
        or report.get("status") != "complete_external_evaluation"
        or report.get("config_id") != "zone-a-phase11.3-evaluation-v1"
    ):
        raise AblationError("Phase 11.3 accepted metrics are required")
    results = report.get("development_ablation")
    if not isinstance(results, dict) or set(results) != set(MODEL_ORDER):
        raise AblationError("development ablation model set is incomplete")
    required = {
        "macro_f1",
        "balanced_accuracy",
        "accuracy",
        "per_class",
        "macro_f1_difference_from_camera_only",
    }
    for name, result in results.items():
        if set(result) != required or set(result["per_class"]) != set(CLASS_LABELS):
            raise AblationError(f"development ablation fields are incomplete for {name}")
        if any("f1" not in result["per_class"][label] for label in CLASS_LABELS):
            raise AblationError(f"per-class F1 is incomplete for {name}")
    return results

def _table(results: dict) -> str:
    lines = [
        "# Phase 11.3 development modality ablation",
        "",
        "All values are frozen development LOSO results. Alternative models were not scored on the external test.",
        "",
        "| Model | Macro F1 | Balanced accuracy | Accuracy | Serving/Processing F1 | Idle/Waiting F1 | Reaching/Handling F1 | Difference from Camera-only |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in MODEL_ORDER:
        result = results[name]
        per_class = result["per_class"]
        lines.append(
            f"| {MODEL_LABELS[name]} | {result['macro_f1']:.6f} | "
            f"{result['balanced_accuracy']:.6f} | {result['accuracy']:.6f} | "
            f"{per_class['Serving/Processing']['f1']:.6f} | "
            f"{per_class['Idle/Waiting']['f1']:.6f} | "
            f"{per_class['Reaching/Handling']['f1']:.6f} | "
            f"{result['macro_f1_difference_from_camera_only']:+.6f} |"
        )
    lines.extend([
        "",
        "Camera A-only remains the overall development choice. Every sensor or early-fusion combination has lower macro F1, so no added model complexity is justified by the frozen development evidence.",
        "",
    ])
    return "\n".join(lines)


def _figure(results: dict, output_path: Path) -> None:
    labels = [MODEL_LABELS[name] for name in MODEL_ORDER]
    macro_f1 = [results[name]["macro_f1"] for name in MODEL_ORDER]
    class_f1 = np.asarray([
        [results[name]["per_class"][label]["f1"] for label in CLASS_LABELS]
        for name in MODEL_ORDER
    ])
    figure, axes = plt.subplots(
        1,
        2,
        figsize=(13, 7.2),
        gridspec_kw={"width_ratios": [1.05, 1.25]},
    )
    figure.suptitle(
        "Phase 11.3 development modality ablation",
        y=0.98,
        fontsize=17,
        fontweight="bold",
        color="#12324a",
    )
    figure.text(
        0.5,
        0.935,
        "Frozen development LOSO evidence only — alternative models were not evaluated on the external test",
        ha="center",
        fontsize=10,
        color="#4f606a",
    )
    figure.subplots_adjust(left=0.22, right=0.93, bottom=0.14, top=0.86, wspace=0.72)
    colors = ["#0b8f87"] + ["#4f83a1"] * 5 + ["#8a969d"]
    positions = np.arange(len(labels))
    axes[0].barh(positions, macro_f1, color=colors, height=0.68)
    axes[0].invert_yaxis()
    axes[0].set_yticks(positions, labels)
    axes[0].set_xlim(0, 0.5)
    axes[0].set_xlabel("Macro F1")
    axes[0].set_title("Overall development performance", loc="left", fontweight="bold")
    axes[0].axvline(macro_f1[0], color="#0b8f87", linestyle="--", linewidth=1.3)
    axes[0].grid(axis="x", color="#d7e0e5", linewidth=0.8)
    axes[0].set_axisbelow(True)
    for position, value in zip(positions, macro_f1):
        axes[0].text(value + 0.006, position, f"{value:.3f}", va="center", fontsize=9)

    image = axes[1].imshow(class_f1, cmap="Blues", vmin=0, vmax=0.75, aspect="auto")
    axes[1].set_title("Per-class development F1", loc="left", fontweight="bold")
    axes[1].set_xticks(np.arange(len(CLASS_LABELS)), [
        "Serving/\nProcessing",
        "Idle/\nWaiting",
        "Reaching/\nHandling",
    ])
    axes[1].set_yticks(np.arange(len(labels)), labels)
    for row in range(class_f1.shape[0]):
        for column in range(class_f1.shape[1]):
            value = class_f1[row, column]
            axes[1].text(
                column,
                row,
                f"{value:.3f}",
                ha="center",
                va="center",
                color="white" if value > 0.42 else "#12324a",
                fontsize=9,
                fontweight="bold" if MODEL_ORDER[row] == "camera_only" else "normal",
            )
    colorbar = figure.colorbar(image, ax=axes[1], shrink=0.82)
    colorbar.set_label("F1")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.stem}.",
            suffix=output_path.suffix,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        figure.savefig(temporary, dpi=200, bbox_inches="tight", facecolor="white")
        os.replace(temporary, output_path)
    finally:
        plt.close(figure)
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def build_ablation_artifacts(
    *,
    metrics_path: str | Path,
    table_path: str | Path,
    figure_path: str | Path,
) -> dict:
    """write the frozen development ablation table and figure"""

    metrics_path = Path(metrics_path)
    table_path = Path(table_path)
    figure_path = Path(figure_path)
    results = _validate(_load_json(metrics_path))
    _write_text_atomic(_table(results), table_path)
    _figure(results, figure_path)
    return {
        "model_count": len(results),
        "selected_model": "camera_only",
        "table_path": str(table_path),
        "figure_path": str(figure_path),
    }