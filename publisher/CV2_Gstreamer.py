#!/usr/bin/python
import sys
import gi
gi.require_version('GLib', '2.0')
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst
import cv2
import time
import CameraData
import globals as G

Gst.init(None)
G.IP_ADDRESS="0.0.0.0"
vehicle_camera=CameraData.GstUdpCamera(9000)
vehicle_camera.play()
while True:
    if not vehicle_camera.new_imgAvaiable:
        print("no data")
        time.sleep(5)
        print("sleeping for 5 seconds")
    img = vehicle_camera.new_imgData
    print(img)
    img_rgb=cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    cv2.imshow("camera", img_rgb)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

