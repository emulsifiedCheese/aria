def extract_tracks(result):
    tracks = []

    if result.boxes is None or result.boxes.id is None:
        return tracks

    boxes = result.boxes.xyxy.cpu().tolist()
    track_ids = result.boxes.id.int().cpu().tolist()
    confidences = result.boxes.conf.cpu().tolist()

    for track_id, box, confidence in zip(track_ids, boxes, confidences):
        x1, y1, x2, y2 = [int(value) for value in box]

        tracks.append(
            {
                "local_track_id": track_id,
                "bounding_box": [x1, y1, x2, y2],
                "detection_confidence": float(confidence),
            }
        )

    return tracks

def extract_pose_tracks(result):
    tracks = extract_tracks(result)

    if not tracks:
        return tracks

    keypoints = getattr(result, "keypoints", None)
    if keypoints is None or keypoints.xy is None:
        for track in tracks:
            track["keypoints"] = []
            track["keypoint_confidences"] = []
        return tracks

    keypoint_positions = keypoints.xy.cpu().tolist()
    if keypoints.conf is None:
        keypoint_confidences = [
            [None] * len(positions)
            for positions in keypoint_positions
        ]
    else:
        keypoint_confidences = keypoints.conf.cpu().tolist()

    for index, track in enumerate(tracks):
        if index >= len(keypoint_positions):
            track["keypoints"] = []
            track["keypoint_confidences"] = []
            continue

        track["keypoints"] = [
            [float(x), float(y)]
            for x, y in keypoint_positions[index]
        ]
        track["keypoint_confidences"] = [
            None if value is None else float(value)
            for value in keypoint_confidences[index]
        ]

    return tracks