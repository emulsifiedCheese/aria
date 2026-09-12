# ARIA Zone A Phase 11.1 baseline policy
## Status and scope
**Policy/config ID:** `zone-a-phase11.1-baselines-v1`  
**Date:** 22 August 2026
Reproducible development baselines are established in Phase 11.1 without access to the locked Phase 10.3 external test. The following baselines are trained and compared:
- Fold-specific majority-class baseline;
- Camera A-only Random Forest;
- ESP-A1-only Random Forest; and
- ESP-A1+ESP-A2 Random Forest.

The majority classifier is the leakage-safe simple baseline. A previous-activity persistence baseline is not used because supplying the preceding true activity during validation would expose information that is unavailable at inference.

## Frozen inputs and features
The machine-readable authority is `config/phase_11_1_baselines.json`. The random seed, class order, candidate grid, modality roots, split policy and SHA-256 hashes of the Phase 10.2 participant features and Phase 10.3 split evidence are locked by this configuration.
Camera A availability, pose availability and camera aggregate features are received by Camera-only models. Only ESP-A1 availability and aggregate features are received by ESP-A1-only models. Only the two nodes' availability and aggregate features are received by ESP-A1+ESP-A2 models. Participant IDs, session IDs, track IDs, timestamps, activity-derived episode IDs and provenance are never included as model inputs.
Missing numerical values are median-imputed inside each training fold, with missingness indicators. A field with no observations in a training fold is retained as a constant placeholder rather than being fitted from validation data. No imputation statistic is fitted on a validation fold. The fixed seed and one worker are used by Random Forest candidates for deterministic training.

## Model selection
Each candidate is evaluated using the eight frozen leave-one-session-out development folds. Macro F1 is the selection metric; balanced accuracy is the first deterministic tie-break, followed by a stable parameter ordering. The selected configuration is then refitted on all development rows and stored locally.
The Phase 10.3 external component is filtered out before feature extraction, fitting, prediction or metric calculation. It remains reserved for one final Phase 11 evaluation after model and hyperparameter selection are frozen.

## Outputs
The baseline workflow can be run with:
```bash
PYTHONPATH=src python3 scripts/train_phase_11_1_baselines.py
```
Local ignored outputs are written to:
- `outputs/evaluation/phase_11_1/baseline_metrics.json`;
- `outputs/evaluation/phase_11_1/model_cards/`; and
- `models/phase_11_1/`.
The config hash, source hashes, seed, class counts, fold metrics, aggregate confusion matrices, candidate results, selected parameters and saved-model hashes are recorded in the metrics report.

## Interpretation limits
Development validation is session-independent but not participant-independent. Results are designated as model-selection evidence and must not be reported as final unseen-participant performance. Reaching/Handling is represented as a sparse minority class. Retained-session operating conditions may be encoded by missingness and device-quality features. The final grouped evaluation, ablations, reliability and latency must be reported in Phase 11.3 before model claims are frozen.