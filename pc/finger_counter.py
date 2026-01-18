import cv2
import mediapipe as mp
import numpy as np
import sys
import os

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
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()

        if not ret or frame is None:
            print(f"[WARN] Failed to read frame {idx}")
            continue

        print(f"[DEBUG] Processing frame {idx}")

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = hands.process(rgb)

        if result.multi_hand_landmarks is None:
            print(f"[DEBUG] No hand detected in frame {idx}")
            continue

        print(f"[DEBUG] HAND DETECTED in frame {idx}")
        detected_frames += 1

        hand_lms = result.multi_hand_landmarks[0]

        if not result.multi_handedness:
            print("[WARN] Hand landmarks found but handedness missing")
            continue

        handedness = result.multi_handedness[0].classification[0].label
        finger_count = count_fingers(hand_lms, handedness)

        print(f"[DEBUG] Frame {idx}: handedness={handedness}, fingers={finger_count}")
        counts.append(finger_count)

        # Optional: save first detected frame
        if detected_frames == 1:
            cv2.imwrite("debug_detected_frame.jpg", frame)
            print("[DEBUG] Saved debug_detected_frame.jpg")

    cap.release()

    print(f"[DEBUG] Frames with hand detected: {detected_frames}/{len(frame_indices)}")

    if not counts:
        print("[DEBUG] No valid finger counts collected")
        return None

    final = int(round(np.median(counts)))
    print(f"[DEBUG] Final finger count (median): {final}")

    return final


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR: No video path provided")
        sys.exit(1)

    video_path = video_path = r"C:\Users\neomu\OneDrive\Desktop\QNX_Project\incoming\clip_20260118_041429.mp4"
    result = classify_video(video_path)

    if result is None:
        print("UNKNOWN")
    else:
        print(result)
