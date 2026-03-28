#!/usr/bin/env python3
"""
Ball Falling Game - Python backend
Detects pink sticky notes via webcam and broadcasts their screen-space
positions over WebSocket to the browser game.

Usage:
    uv run server.py              # auto-picks camera
    uv run server.py --camera 1   # use camera index 1
"""

import cv2
import numpy as np
import asyncio
import websockets
import json
import threading
import time
import os
import argparse

# ── Config ────────────────────────────────────────────────────────────────────
CAMERA_INDEX      = 0  # overridden by --camera arg
WEBSOCKET_HOST    = "localhost"
WEBSOCKET_PORT    = 8765
DETECTION_FPS     = 15
CALIBRATION_FILE  = "calibration.npz"

# Yellow sticky-note HSV ranges (OpenCV: H 0-180, S/V 0-255)
PINK_LOWER_1 = np.array([18,  80,  80])
PINK_UPPER_1 = np.array([35, 255, 255])
PINK_LOWER_2 = np.array([18,  80,  80])  # same — no wrap-around needed for yellow
PINK_UPPER_2 = np.array([35, 255, 255])

MIN_CONTOUR_AREA = 800    # px² — ignore small noise
MAX_CONTOUR_AREA = 60_000 # px² — ignore huge blobs

DEBUG_MODE = False

# ── Shared state (GIL-safe for simple list replacement) ───────────────────────
detected_notes: list[dict] = []
homography: np.ndarray | None = None


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_pink_notes(frame: np.ndarray, H: np.ndarray | None) -> list[dict]:
    """
    Return a list of dicts {x, y, width, height, angle} in screen coordinates.
    If H (homography) is None, returns raw camera coordinates.
    """
    hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.bitwise_or(
        cv2.inRange(hsv, PINK_LOWER_1, PINK_UPPER_1),
        cv2.inRange(hsv, PINK_LOWER_2, PINK_UPPER_2),
    )

    kernel = np.ones((7, 7), np.uint8)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask   = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    notes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not (MIN_CONTOUR_AREA < area < MAX_CONTOUR_AREA):
            continue

        rect              = cv2.minAreaRect(cnt)
        center, (w, h), _ = rect

        if H is not None:
            # Transform all four corners through the homography then re-fit
            box    = cv2.boxPoints(rect).reshape(1, -1, 2).astype(np.float32)
            box_t  = cv2.perspectiveTransform(box, H).reshape(-1, 2)
            rect_t = cv2.minAreaRect(box_t)
            cx, cy = rect_t[0]
            rw, rh = rect_t[1]
            angle  = rect_t[2]
        else:
            cx, cy = center
            rw, rh = w, h
            angle  = rect[2]

        notes.append({
            "x":      float(cx),
            "y":      float(cy),
            "width":  float(max(rw, rh)),
            "height": float(min(rw, rh)),
            "angle":  float(angle),
        })

    return notes


# ── Camera loop (runs in background thread) ───────────────────────────────────

def camera_loop() -> None:
    global detected_notes, homography

    camera_index = CAMERA_INDEX
    if os.path.exists(CALIBRATION_FILE):
        data       = np.load(CALIBRATION_FILE)
        homography = data["H"]
        if "camera_index" in data:
            camera_index = int(data["camera_index"])
        print(f"[camera] Loaded calibration from {CALIBRATION_FILE} (camera {camera_index})")
    else:
        print("[camera] WARNING: no calibration file found — "
              "positions may not align with the projection.")
        print("[camera] Run  uv run calibrate.py  first.")

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"[camera] ERROR: could not open camera {camera_index}")
        return

    interval = 1.0 / DETECTION_FPS
    print(f"[camera] Capturing at {DETECTION_FPS} fps (camera {camera_index})")

    show_debug = DEBUG_MODE
    if show_debug:
        cv2.namedWindow("Debug", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Debug", 960, 540)
        print("[camera] Debug window open — press Q to close it")

    while True:
        t0 = time.monotonic()
        ret, frame = cap.read()
        if ret:
            detected_notes = detect_pink_notes(frame, homography)

            if show_debug:
                hsv  = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                mask = cv2.bitwise_or(
                    cv2.inRange(hsv, PINK_LOWER_1, PINK_UPPER_1),
                    cv2.inRange(hsv, PINK_LOWER_2, PINK_UPPER_2),
                )
                debug = frame.copy()
                # Highlight detected mask in cyan
                debug[mask > 0] = (255, 255, 0)
                # Draw bounding boxes
                for note in detected_notes:
                    cx, cy = int(note["x"]), int(note["y"])
                    cv2.circle(debug, (cx, cy), 8, (0, 255, 0), -1)
                cv2.putText(debug, f"notes: {len(detected_notes)}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
                cv2.imshow("Debug", debug)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    show_debug = False
                    cv2.destroyAllWindows()

        elapsed = time.monotonic() - t0
        time.sleep(max(0.0, interval - elapsed))

    cap.release()


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def ws_handler(websocket) -> None:
    addr = websocket.remote_address
    print(f"[ws] Browser connected: {addr}")
    try:
        while True:
            await websocket.send(json.dumps({"notes": detected_notes}))
            await asyncio.sleep(1.0 / DETECTION_FPS)
    except websockets.exceptions.ConnectionClosed:
        print(f"[ws] Browser disconnected: {addr}")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None,
                        help="Camera index (omit to use calibrate.py's choice or default 0)")
    parser.add_argument("--debug", action="store_true",
                        help="Show live camera window with detection overlay")
    args = parser.parse_args()
    if args.camera is not None:
        global CAMERA_INDEX
        CAMERA_INDEX = args.camera  # overrides calibration file
    global DEBUG_MODE
    DEBUG_MODE = args.debug

    cam_thread = threading.Thread(target=camera_loop, daemon=True)
    cam_thread.start()

    print(f"[ws] Listening on ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    print("[ws] Open index.html in your browser, press F for fullscreen.")

    async with websockets.serve(ws_handler, WEBSOCKET_HOST, WEBSOCKET_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
