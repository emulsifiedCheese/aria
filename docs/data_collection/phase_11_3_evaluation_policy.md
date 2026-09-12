# ARIA Zone A Phase 11.3 evaluation policy
## Status and scope
**Policy/config ID:** `zone-a-phase11.3-evaluation-v1`  
**Config SHA-256:** `0c9b5e491f57a991ab071a5c6fe85b923542f7bd4b01c732137cb0d89c7d0e3a`  
**Date frozen:** 23 August 2026  
**Status:** one-time external evaluation complete; accepted output frozen
The machine-readable authority is `config/phase_11_3_evaluation.json`. The selected model, source and artifact hashes, evaluation metrics, probability-reliability method, development ablation set, missing-modality decisions, latency benchmark and privacy-safe output boundary are frozen by this configuration before the external test is opened.

## Selected model
Camera-only from Phase 11.1 is the final development choice. Its development macro F1 is 0.442791, which is higher than every Phase 11.2 early-fusion candidate. The exact fitted artifact and its Phase 10 and Phase 11 evidence are pinned by SHA-256.
Only this frozen Camera-only artifact may be scored on the external partition. The majority, sensor-only and fusion models remain development-only ablation evidence and must not be used to select another model after external results are known.

## One-time external boundary
Exactly 2,068 rows are included in the external evaluation. Fitting, calibration, parameter changes and output replacement are prohibited. The frozen evaluation pack is written during the first accepted run without an existing result being overwritten. During a later reproducibility check, the pack must be rebuilt into temporary files and compared with the accepted pack rather than the accepted pack being replaced.
The evaluator must be stopped before prediction if any pinned input, split, report or model hash differs. It must also be stopped if the split audit is failed, the external row count differs, any development row is included in the evaluation matrix or any model other than Camera-only is requested.

## Metrics and reliability
Accuracy, balanced accuracy, macro precision, macro recall, macro F1, per-class precision, recall, F1 and support, and the confusion matrix in the frozen class order are included in the accepted report.
The model's unchanged `predict_proba` output is used for reliability assessment. No calibrator is fitted. Multiclass log loss, multiclass Brier score, expected and maximum calibration error using ten equal-width confidence bins, and the number of incorrect predictions whose maximum class probability is at least 0.8 are included in the report.

## Ablation and missing modalities
The frozen development metrics for majority, Camera-only, A1-only, A1+A2, Camera+A1, Camera+A2 and Camera+A1+A2 are consolidated in the ablation table. Alternative candidates are not scored on the external test.
Sensor loss is disregarded by the selected model while Camera A remains available. If Camera A is unavailable, the result is explicitly unavailable rather than silently switching to an unvalidated fallback. No prediction may be produced when every modality is unavailable, and stale predictions must never be reused.

## Latency and privacy
`perf_counter_ns`, 100 warm-up iterations and 1,000 measured iterations at batch sizes 1, 32 and 256 are used in the local benchmark. Latency at p50, p95 and p99 is reported with host and runtime details. Feature flattening and pipeline prediction are included in the measurement; camera capture and dashboard delivery are excluded. Later live integration evidence is required for those end-to-end components.
Only aggregate evaluation outputs may be retained. Participant, session and track IDs, row-level features, raw audio and raw or masked video are excluded from reports and figures.

## Current gate
The frozen Camera-only model was evaluated once on all 2,068 external rows. The accepted result has SHA-256 `52f977c430ab540b823f3c50dc45ae279ffbd1f78f43b951f65631a35f8b355d`. Output replacement is blocked and no fitting, calibration or parameter change occurred.
External macro F1 is 0.348179, balanced accuracy is 0.328030 and accuracy is 0.492263. Reaching/Handling has only 19 rows and none was correctly classified, producing F1 0.000000. No post-result tuning is permitted.
The development ablation table and figure have been completed using frozen development evidence only. All six synthetic missing-modality scenarios were passed under the frozen policy: operation is continued with Camera-only during sensor loss, no prediction is produced during camera loss, and stale activity or confidence is not reused. No participant data or external-test rows were used for these checks. Phase 11.3 is complete with the external Reaching/Handling limitation retained.