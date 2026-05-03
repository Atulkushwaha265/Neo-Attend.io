import os
import platform
import threading
import time

import cv2

_camera_lock = threading.RLock()
_camera = None
_selected_camera_info = None


def _get_max_camera_index():
    """Read the scan limit from the environment with a safe default."""
    raw_value = os.getenv("MAX_CAMERA_INDEX", "6").strip()
    try:
        return max(0, int(raw_value))
    except ValueError:
        return 6


def _get_preferred_camera_index():
    """Optional override when the user knows the exact iVCam index."""
    raw_value = os.getenv("PREFERRED_CAMERA_INDEX", "").strip()
    if raw_value.isdigit():
        return int(raw_value)
    return None


def _get_candidate_backends():
    """Return OpenCV backends in the order that works best on this system."""
    candidates = []

    if platform.system().lower() == "windows":
        if hasattr(cv2, "CAP_DSHOW"):
            candidates.append(("DirectShow", cv2.CAP_DSHOW))
        if hasattr(cv2, "CAP_MSMF"):
            candidates.append(("MediaFoundation", cv2.CAP_MSMF))

    candidates.append(("Default", cv2.CAP_ANY))
    return candidates


def _open_camera(index, backend_id):
    """Open one camera safely without crashing when an index is wrong."""
    try:
        capture = cv2.VideoCapture(index, backend_id)
    except Exception:
        return None

    if capture is None or not capture.isOpened():
        if capture is not None:
            capture.release()
        return None

    return capture


def _read_test_frame(capture, warmup_frames=5):
    """
    Read a few frames so slow-starting cameras like iVCam can settle down.
    Returns a single valid frame, or None if nothing usable arrives.
    """
    frame = None

    for _ in range(warmup_frames):
        ok, frame = capture.read()
        if ok and frame is not None and frame.size > 0:
            return frame
        time.sleep(0.05)

    return None


def _score_camera(camera_info):
    """
    Give extra weight to the devices that are most likely to be iVCam/mobile.

    Heuristic used:
    1. Non-zero indexes are usually external/virtual/mobile cameras.
    2. Higher resolutions are often reported by iVCam more than laptop webcams.
    3. If the user sets PREFERRED_CAMERA_INDEX, that wins immediately.
    """
    score = 0

    preferred_index = _get_preferred_camera_index()
    if preferred_index is not None and preferred_index == camera_info["index"]:
        score += 1000

    if camera_info["index"] != 0:
        score += 100

    width = camera_info["width"]
    height = camera_info["height"]

    if width >= 1280:
        score += 25
    elif width >= 960:
        score += 18
    elif width >= 640:
        score += 10

    if height >= 720:
        score += 10
    elif height >= 480:
        score += 5

    return score


def list_available_cameras(max_index=None):
    """
    Probe camera indexes like 0, 1, 2, 3... and return the working ones.
    """
    if max_index is None:
        max_index = _get_max_camera_index()

    available_cameras = []

    for index in range(max_index + 1):
        for backend_name, backend_id in _get_candidate_backends():
            capture = _open_camera(index, backend_id)
            if capture is None:
                continue

            try:
                frame = _read_test_frame(capture)
                if frame is None:
                    continue

                height, width = frame.shape[:2]
                available_cameras.append(
                    {
                        "index": index,
                        "backend_name": backend_name,
                        "backend_id": backend_id,
                        "width": int(width),
                        "height": int(height),
                    }
                )
                break
            finally:
                capture.release()

    return available_cameras


def select_best_camera(max_index=None):
    """
    Select the best camera dynamically.

    We prefer iVCam/mobile-like devices first, then fall back to the default webcam.
    """
    if max_index is None:
        max_index = _get_max_camera_index()

    available_cameras = list_available_cameras(max_index=max_index)
    if not available_cameras:
        return None

    ranked_cameras = sorted(
        available_cameras,
        key=lambda camera: (
            _score_camera(camera),
            camera["width"] * camera["height"],
            camera["index"],
        ),
        reverse=True,
    )

    selected_camera = ranked_cameras[0].copy()
    selected_camera["score"] = _score_camera(selected_camera)
    selected_camera["available_cameras"] = available_cameras
    return selected_camera


def release_camera():
    """Release the shared camera instance cleanly."""
    global _camera, _selected_camera_info

    with _camera_lock:
        if _camera is not None:
            _camera.release()
        _camera = None
        _selected_camera_info = None


def get_camera(force_refresh=False):
    """
    Initialize the camera only once and reuse it between calls.
    """
    global _camera, _selected_camera_info

    with _camera_lock:
        if force_refresh:
            release_camera()

        if _camera is not None and _camera.isOpened():
            return _camera

        selected_camera = select_best_camera()
        if not selected_camera:
            return None

        capture = _open_camera(selected_camera["index"], selected_camera["backend_id"])
        if capture is None:
            return None

        frame = _read_test_frame(capture)
        if frame is None:
            capture.release()
            return None

        _camera = capture
        _selected_camera_info = selected_camera
        return _camera


def read_camera_frame():
    """
    Read one frame safely.

    If the shared camera stops responding, we release it and try one fresh
    initialization before giving up.
    """
    camera = get_camera()
    if camera is None:
        return None, "No working camera was found. Connect iVCam or a webcam and try again."

    ok, frame = camera.read()
    if ok and frame is not None and frame.size > 0:
        return frame, None

    release_camera()
    camera = get_camera(force_refresh=True)
    if camera is None:
        return None, "Unable to initialize the camera. Please check the iVCam connection."

    ok, frame = camera.read()
    if ok and frame is not None and frame.size > 0:
        return frame, None

    return None, "Camera opened, but no video frame could be read."


def get_selected_camera_info():
    """Return details about the selected shared camera."""
    return _selected_camera_info.copy() if _selected_camera_info else None
