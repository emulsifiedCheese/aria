from ultralytics import YOLO

class PersonDetector:
    def __init__(
        self,
        model_name="yolov8n.pt",
        confidence=0.5,
        iou=0.7,
        tracker_config="config/bytetrack.zone_a.yaml",
        inference_size=640,
        device=None,
    ):
        if (
            not isinstance(iou, (int, float))
            or isinstance(iou, bool)
            or not 0 < iou <= 1
        ):
            raise ValueError("iou must be greater than zero and at most one")
        self.model = YOLO(model_name)
        self.confidence = confidence
        self.iou = float(iou)
        self.tracker_config = tracker_config
        self.inference_size = inference_size
        self.device = device

    def track(self, frame):
        options = {
            "source": frame,
            "persist": True,
            "tracker": self.tracker_config,
            "classes": [0],
            "conf": self.confidence,
            "iou": self.iou,
            "imgsz": self.inference_size,
            "verbose": False,
        }
        if self.device:
            options["device"] = self.device

        results = self.model.track(**options)

        return results[0]

class PoseTracker(PersonDetector):

    def __init__(
        self,
        model_name="yolov8n-pose.pt",
        confidence=0.25,
        iou=0.7,
        tracker_config="config/bytetrack.zone_a.yaml",
        inference_size=640,
        device=None,
    ):
        super().__init__(
            model_name=model_name,
            confidence=confidence,
            iou=iou,
            tracker_config=tracker_config,
            inference_size=inference_size,
            device=device,
        )