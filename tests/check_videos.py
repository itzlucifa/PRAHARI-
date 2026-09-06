import os
import cv2

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
feeds_dir = os.path.join(PROJECT_ROOT, "test_feeds")

for path in [
    os.path.join(feeds_dir, "camera01.mp4"),
    os.path.join(feeds_dir, "camera02.mp4"),
    os.path.join(feeds_dir, "camera03.mp4"),
]:
    cap = cv2.VideoCapture(path)
    if cap.isOpened():
        ret, frame = cap.read()
        if ret:
            print(f"OK: {path} -> {frame.shape}")
        else:
            print(f"FAIL: {path} -> can't read frame")
        cap.release()
    else:
        print(f"FAIL: {path} -> can't open")
