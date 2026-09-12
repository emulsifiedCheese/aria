# ARIA Zone A Phase 11.2 multimodal policy
## Status and scope
**Policy/config ID:** `zone-a-phase11.2-multimodal-v1`  
**Date:** 23 August 2026
Early-fusion Camera+A1, Camera+A2 and Camera+A1+A2 candidates are compared on development data only in Phase 11.2. The Phase 11.1 seed, Random Forest grid, class order, selection metric and deterministic tie-breaks are reused. The accepted Phase 11.1 metrics are frozen as the comparison floor.

## Frozen inputs and features
The machine-readable authority is `config/phase_11_2_multimodal.json`. Seed 3070, the three feature combinations, three Random Forest settings and SHA-256 hashes for the Phase 10.2 features, Phase 10.3 split evidence and Phase 11.1 baseline report are locked by this configuration.
The same eight leave-one-session-out development folds are used for every candidate. Median imputation and missingness indicators are fitted inside each training fold. Participant, session, track, time, annotation, activity-derived episode and provenance identifiers are excluded from model inputs.
The external-test assignments are counted and removed before modelling feature extraction, fitting, prediction or metrics. They remain locked for the final Phase 11 evaluation.

## Model selection
Each Random Forest setting is evaluated across all eight folds. Macro F1 is used as the selection metric, balanced accuracy as the first tie-break, and parameter ordering for the remaining deterministic tie-breaks. The selected setting for each combination is refitted on all development rows and saved locally.
The best multimodal candidate is compared with the accepted Camera-only baseline. A multimodal candidate is not preferred merely because it is more complex. If development macro F1 is not improved, Camera-only is retained as the overall development choice.

## Outputs
The multimodal workflow can be run with:
```bash
PYTHONPATH=src python3 scripts/train_phase_11_2_multimodal.py
```
Local outputs are written to:
- `outputs/evaluation/phase_11_2/multimodal_metrics.json`
- `outputs/evaluation/phase_11_2/model_cards/`
- `models/phase_11_2/`

## Interpretation limits
These results are designated as development model-selection evidence, not final external-test performance. Development validation is session-independent but not participant-independent. Reaching/Handling is sparsely represented, and retained-session operating conditions may be encoded by modality availability. The frozen choice, ablations, missing-modality behaviour, reliability and latency must be evaluated in Phase 11.3 before final claims are made.