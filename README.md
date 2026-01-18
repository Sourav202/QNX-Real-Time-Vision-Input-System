# PiVision
This project demonstrates a distributed vision-processing system built around a Raspberry Pi 5 running QNX and a Windows-based server. The QNX device captures short video clips using a camera module and transmits them to the server, where OpenCV and MediaPipe are used to analyze the footage and extract meaningful visual information. By separating data acquisition on the embedded system from processing on the server, the project illustrates an effective approach to integrating camera-based sensing with a QNX-based platform.


### Python Dependencies

```
pygame
opencv-python
numpy
mediapipe
pynput
```

Install them with:

```bash
pip install -r requirements.txt
```

---

## Project Structure

```
QNX-Real-Time-Vision-Input-System/
│
├── main.py              # Entry point
├── requirements.txt     # Python dependencies
├── README.md            # Project documentation
└── src/                 # Core logic (vision, input handling, utils)
```

*(Structure may vary depending on your local version.)*

---

## Build and Run

### Prerequisites

* Raspberry Pi 5 running QNX with a supported camera module
* Windows machine used as the server and vision processing node
* Python 3.10 installed on Windows
* Network connectivity between the Pi and the Windows machine

---

### 1. Windows Server Setup

1. Navigate to the directory containing `upload_server.py` and `finger_counter.py`.

2. Install the required Python dependencies:

```bash
py -3.10 -m pip install opencv-python mediapipe numpy
```

3. Start the server:

```bash
py -3.10 upload_server.py
```

4. Open a browser and go to:

```
http://localhost:8000/
```

This dashboard is used to trigger recordings and view results.

---

### 2. QNX Raspberry Pi Setup

1. Open `record_agent.sh` and set the IP address of the Windows machine:

```
PC_IP=<windows_ip_address>
```

2. Ensure the camera is connected and accessible on the Pi.

3. Make the script executable and run it:

```sh
chmod +x record_agent.sh
./record_agent.sh
```

The Pi will continuously poll the server for commands.

---

### 3. Running the System

1. Start the server on the Windows machine.
2. Run the recording agent on the QNX Pi.
3. Use the web dashboard to trigger a recording.
4. The Pi records a short video clip and uploads it to the server.
5. The server processes the video and displays the result in the dashboard.


## Acknowledgments

* OpenCV community
* MediaPipe by Google
* QNX real-time systems documentation
