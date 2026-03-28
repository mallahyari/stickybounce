#!/usr/bin/env python3
"""
Calibration tool for Ball Falling Game.

How it works:
  1. Open  index.html?calibrate=1  fullscreen in your browser on the projector.
     Four numbered red dots will appear at the screen corners.
  2. Run this script — it opens your webcam feed.
  3. Click each red dot IN ORDER (1→2→3→4) in the camera window.
  4. The homography is saved to calibration.npz and used by server.py.

Usage:
    uv run calibrate.py              # list cameras, then pick one
    uv run calibrate.py --camera 1   # use camera index 1 directly
"""

import cv2
import numpy as np
import sys
import argparse

CALIBRATION_FILE = "calibration.npz"


def list_cameras(max_test: int = 6) -> list[int]:
    """Return indices of cameras that successfully open."""
    found = []
    for i in range(max_test):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
            cap.release()
    return found


def pick_camera() -> int:
    """Print available cameras and let the user choose."""
    print("Scanning for cameras…")
    indices = list_cameras()
    if not indices:
        print("ERROR: no cameras found.")
        sys.exit(1)
    print(f"Found cameras: {indices}")
    if len(indices) == 1:
        print(f"Using camera {indices[0]} (only one available).")
        return indices[0]
    choice = input(f"Enter camera index to use {indices}: ").strip()
    try:
        idx = int(choice)
        if idx not in indices:
            raise ValueError
        return idx
    except ValueError:
        print(f"Invalid choice — using {indices[0]}")
        return indices[0]


CAMERA_INDEX = 0  # overridden below

# ── These must match CAL_POINTS in index.html (as fractions of canvas W/H) ───
# Default canvas is 1920×1080 — change CANVAS_W / CANVAS_H if you changed it.
CANVAS_W = 1920
CANVAS_H = 1080

SCREEN_POINTS = np.array([
    [CANVAS_W * 0.1, CANVAS_H * 0.1],  # 1 — top-left
    [CANVAS_W * 0.9, CANVAS_H * 0.1],  # 2 — top-right
    [CANVAS_W * 0.9, CANVAS_H * 0.9],  # 3 — bottom-right
    [CANVAS_W * 0.1, CANVAS_H * 0.9],  # 4 — bottom-left
], dtype=np.float32)

LABELS = ["1 - top-left", "2 - top-right", "3 - bottom-right", "4 - bottom-left"]


# ── Mouse callback ────────────────────────────────────────────────────────────

camera_points: list[list[float]] = []
WIN = "Calibration"  # plain ASCII — avoids macOS setMouseCallback bug

def on_click(event, x, y, flags, param) -> None:
    if event == cv2.EVENT_LBUTTONDOWN and len(camera_points) < 4:
        camera_points.append([float(x), float(y)])
        print(f"  Point {len(camera_points)}/4 captured: ({x}, {y})")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None,
                        help="Camera index to use (omit to auto-pick)")
    args = parser.parse_args()

    camera_index = args.camera if args.camera is not None else pick_camera()

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"ERROR: could not open camera {camera_index}")
        sys.exit(1)

    # Create window first, THEN set callback — order matters on macOS
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 960, 540)
    cv2.setMouseCallback(WIN, on_click)

    print("\n=== Calibration ===")
    print(f"Canvas size assumed: {CANVAS_W}x{CANVAS_H}")
    print("Step 1: Open  index.html?calibrate=1  fullscreen on the projector.")
    print("Step 2: Move your mouse to each red dot visible in the camera window.")
    print("        LEFT-CLICK each one IN ORDER: 1 (top-left) -> 2 -> 3 -> 4.")
    print("        Press  Q  to quit without saving.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        display = frame.copy()
        n = len(camera_points)

        # Draw confirmed points
        for i, pt in enumerate(camera_points):
            cv2.circle(display, (int(pt[0]), int(pt[1])), 12, (0, 255, 0), -1)
            cv2.putText(display, str(i + 1), (int(pt[0]) + 15, int(pt[1]) + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        # Instruction
        if n < 4:
            msg = f"LEFT-CLICK dot {n + 1}/4  ({LABELS[n]})"
            color = (0, 200, 255)
        else:
            msg = "All 4 done! Saving..."
            color = (0, 255, 0)

        cv2.rectangle(display, (0, 0), (display.shape[1], 55), (0, 0, 0), -1)
        cv2.putText(display, msg, (15, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.1, color, 2)

        cv2.imshow(WIN, display)

        key = cv2.waitKey(30) & 0xFF  # 30ms — more reliable on macOS than 1ms
        if key == ord('q'):
            print("Calibration cancelled.")
            break

        if len(camera_points) == 4:
            cam_pts = np.array(camera_points, dtype=np.float32)
            H, _    = cv2.findHomography(cam_pts, SCREEN_POINTS)
            np.savez(CALIBRATION_FILE, H=H, camera_index=np.array(camera_index))
            print(f"\nCalibration saved to  {CALIBRATION_FILE}")
            print(f"Camera index {camera_index} saved — just run:  uv run server.py")
            # Brief pause so user sees the "Saving..." message
            cv2.waitKey(1500)
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
