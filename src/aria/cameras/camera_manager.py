import time
from dataclasses import dataclass
import cv2

DEFAULT_CAMERA_WIDTH = 1920
DEFAULT_CAMERA_HEIGHT = 1080
DEFAULT_CAMERA_FPS = 30
FPS_TOLERANCE = 1.0

@dataclass
class CameraStats:
    camera_id: str
    source: object
    requested_width: int
    requested_height: int
    requested_fps: float
    actual_width: int = 0
    actual_height: int = 0
    actual_fps: float = 0.0
    successful_frames: int = 0
    dropped_frames: int = 0

class CameraManager:
    def __init__(
        self,
        camera_id,
        source,
        width=DEFAULT_CAMERA_WIDTH,
        height=DEFAULT_CAMERA_HEIGHT,
        fps=DEFAULT_CAMERA_FPS,
        privacy_mask_status="not_configured",
        enforce_capture_mode=True,
    ):
        self.camera_id = camera_id
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.privacy_mask_status = privacy_mask_status
        self.enforce_capture_mode = enforce_capture_mode
        self.capture = None
        self.stats = CameraStats(
            camera_id=camera_id,
            source=source,
            requested_width=width,
            requested_height=height,
            requested_fps=fps,
        )

    def open(self):
        self.capture = cv2.VideoCapture(self.source)

        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open camera {self.camera_id} using source {self.source}")

        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.capture.set(cv2.CAP_PROP_FPS, self.fps)

        self.stats.actual_width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.stats.actual_height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.stats.actual_fps = self.capture.get(cv2.CAP_PROP_FPS)
        if self.enforce_capture_mode:
            self._validate_capture_mode()

    def _validate_capture_mode(self):
        resolution_matches = (self.stats.actual_width == self.width and self.stats.actual_height == self.height)
        fps_matches = (self.stats.actual_fps > 0 and abs(self.stats.actual_fps - self.fps) <= FPS_TOLERANCE)

        if resolution_matches and fps_matches:
            return

        self.close()
        raise RuntimeError(
            f"Camera {self.camera_id} did not provide the required capture mode: "
            f"requested {self.width}x{self.height}@{self.fps}fps, got "
            f"{self.stats.actual_width}x{self.stats.actual_height}@"
            f"{self.stats.actual_fps:.2f}fps"
        )

    def read(self):
        if self.capture is None:
            raise RuntimeError("Camera has not been opened")

        success, frame = self.capture.read()

        if success:
            self.stats.successful_frames += 1
            return frame

        self.stats.dropped_frames += 1
        return None

    def run_preview(self, duration_seconds=15):
        self.open()
        started_at = time.monotonic()
        window_name = f"ARIA Camera Diagnostic - {self.camera_id}"

        print(self.summary())

        try:
            while time.monotonic() - started_at < duration_seconds:
                frame = self.read()

                if frame is None:
                    continue

                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(
                    frame,
                    f"{self.camera_id} | {timestamp}",
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                )

                cv2.imshow(window_name, frame)

                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        finally:
            self.close()
            cv2.destroyAllWindows()

        print(self.summary())

    def summary(self):
        return (
            f"Camera ID: {self.stats.camera_id}\n"
            f"Source: {self.stats.source}\n"
            f"Requested resolution: "
            f"{self.stats.requested_width}x{self.stats.requested_height}\n"
            f"Actual resolution: "
            f"{self.stats.actual_width}x{self.stats.actual_height}\n"
            f"Requested FPS: {self.stats.requested_fps}\n"
            f"Actual FPS: {self.stats.actual_fps:.2f}\n"
            f"Successful frames: {self.stats.successful_frames}\n"
            f"Dropped frames: {self.stats.dropped_frames}\n"
            f"Privacy mask status: {self.privacy_mask_status}"
        )

    def close(self):
        if self.capture is not None:
            self.capture.release()
            self.capture = None