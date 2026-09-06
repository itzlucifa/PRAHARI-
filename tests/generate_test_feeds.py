"""
Generate synthetic test video feeds simulating different camera types.
Creates 3 test videos with moving colored rectangles (simulating people/vehicles).
Run: python tests/generate_test_feeds.py
"""
import cv2
import numpy as np
import os


def create_test_video(filename: str, width: int, height: int, fps: int, duration: int, objects: list):
    """
    Create a test video with moving objects.
    objects: list of dicts with keys: color, start_pos, end_pos, label
    """
    frames = fps * duration
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    
    for i in range(frames):
        frame = np.random.randint(0, 30, (height, width, 3), dtype=np.uint8)
        
        for obj in objects:
            t = i / frames
            x = int(obj["start"][0] + (obj["end"][0] - obj["start"][0]) * t)
            y = int(obj["start"][1] + (obj["end"][1] - obj["start"][1]) * t)
            size = obj.get("size", 40)
            color = obj["color"]
            label = obj.get("label", "")
            
            cv2.rectangle(frame, (x-size//2, y-size//2), (x+size//2, y+size//2), color, -1)
            if label:
                cv2.putText(frame, label, (x-15, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255), 1)
        
        # Add timestamp overlay (important for live-feed realism)
        ts = f"Frame {i}/{frames} ({i/fps:.1f}s)"
        cv2.putText(frame, ts, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        writer.write(frame)
    
    writer.release()
    print(f"Created {filename} ({width}x{height}, {duration}s, {fps}fps)")


if __name__ == "__main__":
    test_dir = os.path.join(os.path.dirname(__file__), "..", "test_feeds")
    os.makedirs(test_dir, exist_ok=True)
    
    # Camera 1: Standard resolution (640x480), person + vehicle
    create_test_video(
        os.path.join(test_dir, "camera01.mp4"),
        640, 480, 15, 10,
        objects=[
            {"color": (0, 255, 0), "start": (50, 240), "end": (590, 240), "size": 30, "label": "PERSON"},
            {"color": (0, 0, 255), "start": (100, 400), "end": (500, 100), "size": 50, "label": "VEHICLE"},
        ]
    )
    
    # Camera 2: Low resolution (320x240), simulating old camera
    create_test_video(
        os.path.join(test_dir, "camera02.mp4"),
        320, 240, 15, 10,
        objects=[
            {"color": (0, 255, 0), "start": (30, 120), "end": (290, 120), "size": 20, "label": "PERSON"},
        ]
    )
    
    # Camera 3: Different aspect (1280x720), simulating phone IP cam
    create_test_video(
        os.path.join(test_dir, "camera03.mp4"),
        1280, 720, 15, 10,
        objects=[
            {"color": (255, 0, 0), "start": (100, 360), "end": (1180, 360), "size": 60, "label": "VEHICLE"},
            {"color": (0, 255, 0), "start": (640, 500), "end": (640, 100), "size": 40, "label": "PERSON"},
        ]
    )
    
    print("\n=== Test feeds generated in tests/test_feeds/ ===")
