import sys
import os

# Optional: auto-relaunch with Python 3.10 on Windows (MediaPipe compatibility)
# If you don't want this behavior, delete this block.
if os.name == "nt":
    try:
        if sys.version_info[:2] != (3, 10):
            import subprocess
            print("[INFO] Re-launching with Python 3.10 (py -3.10)...")
            subprocess.check_call(["py", "-3.10"] + sys.argv)
            raise SystemExit(0)
    except FileNotFoundError:
        # 'py' launcher not installed; continue and let import errors happen if any
        pass

import time
import glob
import subprocess
import cv2
import mediapipe as mp
import numpy as np

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=True,
    max_num_hands=1,
    min_detection_confidence=0.6
)

TIP_IDS = [4, 8, 12, 16, 20]


def count_fingers(hand_landmarks, handedness):
    lm = hand_landmarks.landmark
    fingers = 0

    # Thumb
    if handedness == "Right":
        if lm[TIP_IDS[0]].x < lm[TIP_IDS[0] - 1].x:
            fingers += 1
    else:
        if lm[TIP_IDS[0]].x > lm[TIP_IDS[0] - 1].x:
            fingers += 1

    # Other fingers
    for i in range(1, 5):
        if lm[TIP_IDS[i]].y < lm[TIP_IDS[i] - 2].y:
            fingers += 1

    return fingers


def classify_video(video_path, sample_frames=30):
    # Keep debug prints if you want; the LAST line printed by main will be the answer.
    print(f"[DEBUG] Opening video: {video_path}")

    if not os.path.exists(video_path):
        print("[ERROR] File does not exist")
        return None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("[ERROR] cv2.VideoCapture failed to open video")
        return None

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[DEBUG] Total frames reported: {total_frames}")

    if total_frames <= 0:
        print("[ERROR] No frames in video")
        cap.release()
        return None

    frame_indices = np.linspace(0, total_frames - 1, sample_frames, dtype=int)
    print(f"[DEBUG] Sampling {len(frame_indices)} frames")

    counts = []
    detected_frames = 0

    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()

        if not ret or frame is None:
            print(f"[WARN] Failed to read frame {idx}")
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        if result.multi_hand_landmarks is None:
            continue

        detected_frames += 1
        hand_lms = result.multi_hand_landmarks[0]

        if not result.multi_handedness:
            continue

        handedness = result.multi_handedness[0].classification[0].label
        finger_count = count_fingers(hand_lms, handedness)
        counts.append(finger_count)

        # Optional: save first detected frame
        if detected_frames == 1:
            cv2.imwrite("debug_detected_frame.jpg", frame)
            print("[DEBUG] Saved debug_detected_frame.jpg")

    cap.release()

    print(f"[DEBUG] Frames with hand detected: {detected_frames}/{len(frame_indices)}")

    if not counts:
        return None

    final = int(round(np.median(counts)))
    print(f"[DEBUG] Final finger count (median): {final}")
    return final


def newest_mp4_in(dirpath: str):
    files = glob.glob(os.path.join(dirpath, "*.mp4"))
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def trigger_and_wait_then_classify(
    seconds=5,
    expected=3,
    trigger_url_base="http://localhost:8000",
    incoming_dir=None,
    timeout_s=90,
    poll_interval_s=0.5,
):
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # IMPORTANT: incoming is one directory higher than /pc
    if incoming_dir is None:
        incoming_dir = os.path.abspath(os.path.join(script_dir, "..", "incoming"))

    os.makedirs(incoming_dir, exist_ok=True)

    before = newest_mp4_in(incoming_dir)
    before_ts = os.path.getmtime(before) if before else 0
    print(f"[INFO] Incoming dir: {incoming_dir}")
    print(f"[INFO] Newest before: {before}")

    url = f"{trigger_url_base}/trigger?seconds={seconds}&expected={expected}"
    print(f"[INFO] Triggering: {url}")

    # Use curl.exe like you requested
    r = subprocess.run(["curl.exe", "-sS", url], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[ERROR] curl.exe failed (rc={r.returncode})")
        if r.stderr:
            print(r.stderr.strip())
        return 2

    print(f"[INFO] Trigger response: {r.stdout.strip()}")

    print(f"[INFO] Waiting for new upload in '{incoming_dir}' (timeout {timeout_s}s)...")
    deadline = time.time() + timeout_s
    new_file = None

    while time.time() < deadline:
        cand = newest_mp4_in(incoming_dir)
        if cand:
            ts = os.path.getmtime(cand)
            if ts > before_ts and cand != before:
                # small settle time so file write finishes
                time.sleep(0.25)
                new_file = cand
                break
        time.sleep(poll_interval_s)

    if not new_file:
        print("UNKNOWN")
        print("[ERROR] Timed out waiting for a new mp4 upload.")
        return 3

    print(f"[INFO] Got new upload: {new_file}")

    result = classify_video(new_file)
    if result is None:
        print("UNKNOWN")
        return 1

    # FINAL answer line (server logic uses last non-empty line)
    print(result)
    return 0


if __name__ == "__main__":
    # Mode A: classify explicit file (used by upload_server)
    #   py -3.10 finger_counter.py ..\incoming\clip_....mp4
    #
    # Mode B: no args -> trigger Pi, wait for upload, then classify newest file
    #   py -3.10 finger_counter.py
    if len(sys.argv) >= 2:
        video_path = sys.argv[1]
        result = classify_video(video_path)
        if result is None:
            print("UNKNOWN")
            sys.exit(1)
        print(result)
        sys.exit(0)
    else:
        sys.exit(trigger_and_wait_then_classify(seconds=5, expected=3))
