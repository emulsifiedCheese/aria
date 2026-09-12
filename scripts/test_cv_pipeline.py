#!/usr/bin/env python3
"""run masked camera a detection, tracking and pose pipeline"""
import argparse
from pathlib import Path
import yaml
from aria.cameras.privacy_mask import MaskConfig
from aria.vision.pipeline import CVPipeline

def load_mask(path: str | Path, camera_id: str) -> MaskConfig:
    with Path(path).open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    mask = config["masks"][camera_id]

    return MaskConfig(
        camera_id=mask["camera_id"],
        expected_width=mask["expected_width"],
        expected_height=mask["expected_height"],
        x=mask["x"],
        y=mask["y"],
        width=mask["width"],
        height=mask["height"],
        verified=mask["verified"],
        excluded_polygons=mask.get("excluded_polygons", []),
        mask_config_version=mask.get(
            "mask_config_version",
            "unversioned",
        ),
    )

def normalise_source(source: str):
    return int(source) if source.isdigit() else source

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the ARIA initial CV pipeline."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Video file path or camera index",
    )
    parser.add_argument(
        "--camera-id",
        default="camera_a",
        choices=["camera_a"],
    )
    parser.add_argument(
        "--mask-config",
        required=True,
        help=(
            "Explicit privacy-mask configuration. Use the verified deployment "
            "mask for live Camera A; the development mask is permitted only "
            "for non-research test video."
        ),
    )
    parser.add_argument(
        "--output",
        default="data/interim/camera_a_tracks.jsonl",
    )
    parser.add_argument(
        "--detector-model",
        default="yolov8n.pt",
    )
    parser.add_argument(
        "--detector-confidence",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--detector-iou",
        type=float,
        default=0.7,
        help="YOLO person-detection NMS IoU threshold",
    )
    parser.add_argument(
        "--pose-model",
        default="yolov8n-pose.pt",
    )
    parser.add_argument(
        "--pose-confidence",
        type=float,
        default=0.25,
    )
    parser.add_argument(
        "--tracker-config",
        default="config/bytetrack.zone_a.yaml",
    )
    parser.add_argument(
        "--tracking-only",
        action="store_true",
        help="Run masked person detection and tracking without pose inference",
    )
    parser.add_argument(
        "--processing-fps",
        type=float,
        default=15.0,
        help="Maximum CV processing rate; Camera A remains at 30 FPS",
    )
    parser.add_argument(
        "--inference-size",
        type=int,
        default=640,
        help="Person detector input size after the privacy mask",
    )
    parser.add_argument(
        "--pose-inference-size",
        type=int,
        default=384,
        help="Pose-model input size for each tracked-person crop",
    )
    parser.add_argument(
        "--device",
        help="Optional Ultralytics device such as cpu or mps",
    )
    parser.add_argument(
        "--experimental-track-stitching",
        action="store_true",
        help=(
            "Overlay and record conservative anonymous stitched IDs; "
            "non-research validation only"
        ),
    )
    parser.add_argument(
        "--duration",
        type=float,
        help="Optional automatic stop duration in seconds",
    )
    parser.add_argument(
        "--keypoint-confidence",
        type=float,
        default=0.5,
        help="Confidence required for a keypoint to support a valid pose",
    )
    parser.add_argument(
        "--min-confident-keypoints",
        type=int,
        default=5,
        help="Minimum supporting keypoints required to retain a pose track",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Run without opening a preview window",
    )
    return parser

def main(argv=None) -> None:
    args = build_parser().parse_args(argv)

    mask_config = load_mask(
        path=args.mask_config,
        camera_id=args.camera_id,
    )

    pipeline = CVPipeline(
        camera_id=args.camera_id,
        source=normalise_source(args.source),
        mask_config=mask_config,
        output_path=args.output,
        display=not args.no_display,
        detector_model=args.detector_model,
        detector_confidence=args.detector_confidence,
        detector_iou=args.detector_iou,
        pose_model=args.pose_model,
        pose_confidence=args.pose_confidence,
        tracker_config=args.tracker_config,
        tracking_only=args.tracking_only,
        processing_fps=args.processing_fps,
        inference_size=args.inference_size,
        pose_inference_size=args.pose_inference_size,
        device=args.device,
        duration_seconds=args.duration,
        keypoint_confidence=args.keypoint_confidence,
        min_confident_keypoints=args.min_confident_keypoints,
        experimental_track_stitching=args.experimental_track_stitching,
    )

    pipeline.run()


if __name__ == "__main__":
    main()
