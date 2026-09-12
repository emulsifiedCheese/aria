from ultralytics import YOLO

class PoseEstimator:
    def __init__(
        self,
        model_name="yolov8n-pose.pt",
        confidence=0.25,
        inference_size=640,
        device=None,
    ):
        self.model = YOLO(model_name)
        self.confidence = confidence
        self.inference_size = inference_size
        self.device = device

    def estimate(self, frame, bounding_box):
        x1, y1, x2, y2 = bounding_box
        crop = frame[y1:y2, x1:x2]

        if crop.size == 0:
            return [], []

        results = self.model.predict(source=crop,conf=self.confidence,verbose=False,)

        result = results[0]

        if result.keypoints is None or result.keypoints.xy is None:
            return [], []

        if len(result.keypoints.xy) == 0:
            return [], []

        keypoints = result.keypoints.xy[0].cpu().tolist()

        if result.keypoints.conf is None:
            confidences = [None] * len(keypoints)
        else:
            confidences = result.keypoints.conf[0].cpu().tolist()

        translated = []

        for x, y in keypoints:
            translated.append([float(x + x1), float(y + y1)])

        return translated, [
            None if value is None else float(value)
            for value in confidences
        ]

    def estimate_many(self, frame, bounding_boxes):
        outputs = [([], []) for _ in bounding_boxes]
        crops = []
        crop_metadata = []

        for index, bounding_box in enumerate(bounding_boxes):
            x1, y1, x2, y2 = bounding_box
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            crops.append(crop)
            crop_metadata.append((index, x1, y1))

        if not crops:
            return outputs

        options = {
            "source": crops,
            "conf": self.confidence,
            "imgsz": self.inference_size,
            "verbose": False,
        }
        if self.device:
            options["device"] = self.device
        results = self.model.predict(**options)

        for result, (index, offset_x, offset_y) in zip(
            results,
            crop_metadata,
        ):
            if (
                result.keypoints is None
                or result.keypoints.xy is None
                or len(result.keypoints.xy) == 0
            ):
                continue

            pose_index = 0
            if result.boxes is not None and len(result.boxes) > 1:
                pose_index = int(result.boxes.conf.argmax().item())

            positions = result.keypoints.xy[pose_index].cpu().tolist()
            if result.keypoints.conf is None:
                confidences = [None] * len(positions)
            else:
                confidences = (
                    result.keypoints.conf[pose_index].cpu().tolist()
                )

            outputs[index] = (
                [
                    [float(x + offset_x), float(y + offset_y)]
                    for x, y in positions
                ],
                [
                    None if value is None else float(value)
                    for value in confidences
                ],
            )

        return outputs