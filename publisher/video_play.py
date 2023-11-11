import cv2
import numpy as np

cap = cv2.VideoCapture("./video.mp4")
cap.set(3, 160)
cap.set(4, 120)
while True:
    ret, frame = cap.read()
    cv2.imshow("Frame", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):  # 1 is the time in ms
        break
    
cap.release()
cv2.destroyAllWindows()
