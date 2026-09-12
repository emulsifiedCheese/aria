from aria.vision.tracker import extract_pose_tracks

class FakeTensor:
    def __init__(self, value):
        self.value = value

    def cpu(self):
        return self

    def int(self):
        return FakeTensor(
            [int(value) for value in self.value]
        )

    def tolist(self):
        return self.value

class FakeBoxes:
    xyxy = FakeTensor([[10.2, 20.8, 100.1, 200.9]])
    id = FakeTensor([7])
    conf = FakeTensor([0.85])

class FakeKeypoints:
    xy = FakeTensor([[[20.0, 30.0], [40.0, 50.0]]])
    conf = FakeTensor([[0.9, 0.8]])

class FakeResult:
    boxes = FakeBoxes()
    keypoints = FakeKeypoints()

def test_extract_pose_tracks_keeps_ids_boxes_and_keypoints_aligned():
    tracks = extract_pose_tracks(FakeResult())

    assert tracks == [
        {
            "local_track_id": 7,
            "bounding_box": [10, 20, 100, 200],
            "detection_confidence": 0.85,
            "keypoints": [[20.0, 30.0], [40.0, 50.0]],
            "keypoint_confidences": [0.9, 0.8],
        }
    ]