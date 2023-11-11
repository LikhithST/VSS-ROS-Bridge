import cv2
import numpy as np

cap = cv2.VideoCapture("udpsrc port=9000 ! application/x-rtp,payload=96,encoding-name=H264 ! rtpjitterbuffer mode=1 ! rtph264depay ! h264parse ! decodebin ! videoconvert ! appsink", cv2.CAP_GSTREAMER);

# cap.set(3, 160)
# cap.set(4, 120)
while True:
    ret, frame = cap.read()
    print(frame)
    cv2.imshow("Frame", frame)
    
    if cv2.waitKey(1) & 0xFF == ord("q"):  # 1 is the time in ms
        break
    
cap.release()
cv2.destroyAllWindows()
