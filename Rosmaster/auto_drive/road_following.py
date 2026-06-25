import torch
import torchvision

from torch2trt import TRTModule

from utils import preprocess
import numpy as np

from Rosmaster_Lib import Rosmaster
import time

from jetcam.usb_camera import USBCamera

import cv2 as cv


print("load model trt")
model_trt = TRTModule()
model_trt.load_state_dict(torch.load('road_following_model_trt.pth'))

print("load Rosmaster")
car = Rosmaster()
print("load camera")
camera = USBCamera(width=224, height=224)


STEERING_GAIN = 45
STEERING_BIAS = 0.00

speed = 0.3

car.set_beep(100)
time.sleep(.2)
car.set_car_motion(speed, 0, 0)

print("start program")
try:
    while True:
        action = cv.waitKey(10) & 0xFF
        image = camera.read()
        frame = image.copy()
        cv.imshow('frame', frame)
        image = preprocess(image).half()
        output = model_trt(image).detach().cpu().numpy().flatten()
        x = float(output[0])
        fvalue = x * STEERING_GAIN + STEERING_BIAS
        car.set_akm_steering_angle(fvalue, True)
        print("car:", fvalue)
        # car.set_car_motion(speed, fvalue, 0)
except:
    pass

del camera
cv.destroyAllWindows()
car.set_car_motion(0, 0, 0)
