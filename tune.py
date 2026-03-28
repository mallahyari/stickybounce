#!/usr/bin/env python3
"""
Detection tuning tool — run this standalone to check if pink notes are detected.
Shows live camera feed with cyan highlight where pink is detected.
Press Q to quit.

Usage:
    uv run tune.py
    uv run tune.py --camera 1
"""

import cv2
import numpy as np
import argparse
import sys

# ── These must match server.py ─────────────────────────────────────────────────
PINK_LOWER_1 = np.array([18,  80,  80])
PINK_UPPER_1 = np.array([35, 255, 255])
PINK_LOWER_2 = np.array([18,  80,  80])
PINK_UPPER_2 = np.array([35, 255, 255])
MIN_CONTOUR_AREA = 800
MAX_CONTOUR_AREA = 60_000


def list_cameras(max_test: int = 6) -> list[int]:
    found = []
    for i in range(max_test):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
            cap.release()
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None)
    args = parser.parse_args()

    if args.camera is not None:
        camera_index = args.camera
    else:
        indices = list_cameras()
        if not indices:
            print("No cameras found.")
            sys.exit(1)
        camera_index = indices[-1]  # last = most recently added (iPhone)
        print(f"Using camera {camera_index}  (all found: {indices})")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"ERROR: could not open camera {camera_index}")
        sys.exit(1)

    cv2.namedWindow("Detection Tuning", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Detection Tuning", 960, 540)
    print("Hold a pink sticky note in front of the camera.")
    print("It should turn CYAN when detected. Press Q to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.bitwise_or(
            cv2.inRange(hsv, PINK_LOWER_1, PINK_UPPER_1),
            cv2.inRange(hsv, PINK_LOWER_2, PINK_UPPER_2),
        )

        kernel = np.ones((7, 7), np.uint8)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        display = frame.copy()
        display[mask > 0] = (255, 255, 0)  # cyan highlight

        count = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if MIN_CONTOUR_AREA < area < MAX_CONTOUR_AREA:
                count += 1
                rect = cv2.minAreaRect(cnt)
                box  = cv2.boxPoints(rect).astype(np.int32)
                cv2.drawContours(display, [box], 0, (0, 255, 0), 2)

        status = f"Detected: {count} note(s)"
        cv2.rectangle(display, (0, 0), (350, 45), (0, 0, 0), -1)
        cv2.putText(display, status, (8, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                    (0, 255, 0) if count else (0, 80, 255), 2)

        cv2.imshow("Detection Tuning", display)
        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
