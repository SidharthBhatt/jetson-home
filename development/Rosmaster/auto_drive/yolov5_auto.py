#!/usr/bin/env python3
# encoding: utf-8
import base64
import sys
import time
import cv2 as cv
from yolov5_trt import YoLov5TRT
import numpy as np
import threading

import torch
from torch2trt import TRTModule
from utils import preprocess

from Rosmaster_Lib import Rosmaster
import time


class YoloDetect:
    def __init__(self):
        self.device = "nano4G"
        self.yolo_busy = False
        self.yolo_start = False
        self.car_enable = False
        self.auto_control = False
        self.road_sign_count = 1
        self.car_state = 1
        self.car_start = False
        self.car_speed = 0.2


    def cancel(self):
        if self.car_enable:
            self.car_stop()
            self.car_enable = False
    
        if self.yolo_start:
            while self.yolo_busy:
                pass
            self.yolov5_wrapper.destroy()
            self.yolo_start = False
            
        
    
    def load_yolo(self):
        #param_ = "/home/jetson/ROS/R2L/yahboomcar_ws/src/yahboomcar_yolov5/param/"
        param_ = "/home/jetson/Rosmaster/auto_drive/yolov5/"
        file_yaml = param_ + 'traffic.yaml'
        PLUGIN_LIBRARY = param_ + self.device + "/libmyplugins.so"
        engine_file_path = param_ + self.device + "/yolov5s.engine"
        self.yolov5_wrapper = YoLov5TRT(file_yaml, PLUGIN_LIBRARY, engine_file_path)
        self.yolo_start = True

    def detect(self, frame):
        try:
            score = -0.1
            classid = -1
            index = 0
            frame, result_boxes, result_scores, result_classid = self.yolov5_wrapper.infer(frame)
            for i in range(len(result_scores)):
                if result_scores[i] > score:
                    index = i
                    score = float(result_scores[i])
                    classid = int(result_classid[i])
            if len(result_boxes) > 0:
                box = result_boxes[index]
                text ="{}:{:.2f}".format(self.yolov5_wrapper.categories[classid], score)
                self.yolov5_wrapper.plot_one_box(box, frame, label=text)
                return frame, classid, score, box
        except:
            pass
        return frame, 0, 0, [0, 0, 0, 0]
    
    def car_stop(self):
        self.auto_control = False
        self.car.set_car_motion(0, 0, 0)
        
    def car_run(self):
        self.car.set_car_motion(self.car_speed , 0, 0)
        self.auto_control = True
        self.car_state = 1
    
    def car_turn_right(self):
        time.sleep(5)
        self.auto_control = False
        time.sleep(.1)
        for i in range(20):
            self.car.set_car_motion(self.car_speed , 0, -3.0)
            time.sleep(.1)
        self.auto_control = True

    def car_whistle(self):
        self.car.set_beep(500)
        time.sleep(.5)
    
    def car_sidewalk(self):
        self.auto_control = False
        time.sleep(.1)
        self.car_stop()
        time.sleep(2)
        self.car_run()
        self.auto_control = True
        time.sleep(3)
    
    def car_limiting_velocity(self):
        self.auto_control = True
        self.car.set_car_motion(0.4 , 0, 0)
        time.sleep(3)
        self.car.set_car_motion(self.car_speed , 0, 0)
        
    def car_shutdown(self):
        self.auto_control = False
        time.sleep(.1)
        self.car_stop()
        
    def car_school_decelerate(self):
        self.auto_control = True
        self.car.set_car_motion(0.1 , 0, 0)
        time.sleep(5)
        self.car.set_car_motion(self.car_speed , 0, 0)
    
    def car_parking(self):
        self.car.set_car_motion(0, 0, 0)
        time.sleep(1)
        self.car.set_car_motion(0.25, 0, 0)
        time.sleep(5)
        self.auto_control = False
        self.car.set_car_motion(0, 0, 0)
        time.sleep(.1)
        self.car.set_car_motion(-0.25, 0, 1.5)
        time.sleep(4)
        self.car.set_car_motion(-0.25, 0, 0)
        time.sleep(1)
        self.car.set_car_motion(0, 0, 0)
        
    def car_no_light(self):
        self.car_run()
        time.sleep(5)
        

    
    def car_red_light(self):
        if self.car_state == 1:
            self.auto_control = False
            self.car_stop()
            time.sleep(.5)
            self.car.set_car_motion(-self.car_speed , 0, 0.01)
            time.sleep(2)
            self.car_stop()
            time.sleep(.1)
            self.car_state = 0
    
    def cal_box_area(self, box):
        area = 0
        width = int(box[2] - box[0])
        height = int(box[3] - box[1])
        area = width * height
        return area
    
    # categories: ["Go_straight","Turn_right","whistle","Sidewalk","Limiting_velocity","Shutdown","School_decelerate","Parking_lotB","Parking_lotA","No_light","Red_light"]
    def control_car(self, classid, score, box):
        if classid >= 0:
            # print("classid:", classid)
            detect_classid = int(classid)
            detect_score = float(score)
            area = self.cal_box_area(box)
            # if detect_score < 0.7 or area < 2000:
            if (detect_score < 0.7 or area < 2000) and detect_classid < 9:
                # print("detect_classid:", detect_classid)
                return
            print("detect_classid:", detect_classid, self.yolov5_wrapper.categories[detect_classid], detect_score, area)
            # print("box:", area, box[0], box[1], box[2], box[3])
            
            if detect_classid == 0: # Go_straight
                self.car_run()
            elif detect_classid == 1: # Turn_right
                self.car_turn_right()
            elif detect_classid == 2: # whistle
                self.car_whistle()
            elif detect_classid == 3: # Sidewalk
                self.car_sidewalk()
            elif detect_classid == 4: # Limiting_velocity
                self.car_limiting_velocity()
            elif detect_classid == 5: # Shutdown
                self.car_shutdown()
            elif detect_classid == 6: # School_decelerate
                self.car_school_decelerate()
            elif detect_classid == 8 or detect_classid == 7: # Parking_lotA
                self.car_parking()
            elif detect_classid == 9: # No_light
                self.car_no_light()
            elif detect_classid == 10: # Red_light
                self.car_red_light()
    
    def thread_detect(self, frame):
        image, classid, score, box = self.detect(frame)
        # print("detect_classid:", classid, self.yolov5_wrapper.categories[classid], score)
        self.control_car(classid, score, box)
        self.yolo_busy = False
    
    def yolo_detect(self, image):
        if not self.yolo_busy:
            self.yolo_busy = True
            task_yolo = threading.Thread(target=self.thread_detect, args=(image,), name="task_yolo")
            task_yolo.setDaemon(True)
            task_yolo.start()
        return image
        

    def load_model_trt(self):
        print("load model trt")
        self.model_trt = TRTModule()
        self.model_trt.load_state_dict(torch.load('road_following_model_trt.pth'))
        
        
    def cal_road_following(self, image):
        STEERING_GAIN = 60
        STEERING_BIAS = 0.00
        image = cv.resize(image, (224, 224))
        image = preprocess(image).half()
        output = self.model_trt(image).detach().cpu().numpy().flatten()
        x = float(output[0])
        fvalue = x * STEERING_GAIN + STEERING_BIAS
        return fvalue
    
    def load_car(self):
        self.car = Rosmaster()
        self.car.set_beep(100)
        self.car_enable = True
        
    def car_control(self, value):
        if self.auto_control:
            self.car.set_akm_steering_angle(value, True)
    
        
if __name__ == "__main__":
    print("Python version: ", sys.version)
    # capture = cv.VideoCapture(0)
    capture = cv.VideoCapture("/dev/camera_wide_angle")
    capture.set(6, cv.VideoWriter.fourcc('M', 'J', 'P', 'G'))
    capture.set(cv.CAP_PROP_FRAME_WIDTH, 640)
    capture.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
    # capture.set(cv.CAP_PROP_FRAME_WIDTH, 320)
    # capture.set(cv.CAP_PROP_FRAME_HEIGHT, 240)
    print("capture get FPS : ", capture.get(cv.CAP_PROP_FPS))
    detect = YoloDetect()
    detect.load_yolo()
    detect.load_model_trt()
    detect.load_car()
    cTime = 0
    pTime = 0
    t_start = time.time()
    m_fps = 0
    load_opencv = 0
    # detect.car_run()
    try:
        while capture.isOpened():
            ret, frame = capture.read()
            action = cv.waitKey(10) & 0xFF
            if action == ord('q'): break
            # frame, classid = detect.detect(frame)
            # print("classid:", classid)
            detect.yolo_detect(frame)

            car_value = detect.cal_road_following(frame)
            # print("car_value:", car_value)
            detect.car_control(car_value)
            
            m_fps = m_fps + 1
            fps = m_fps / (time.time() - t_start)
            if(time.time() - t_start >= 2000):
                t_start = time.time()
                m_fps = fps
            # cTime = time.time()
            # fps = 1 / (cTime - pTime)
            # pTime = cTime
            text = "FPS: " + str(int(fps))
            cv.putText(frame, text, (20, 30), cv.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 1)
            cv.imshow('frame', frame)
            # print(text)
            if load_opencv == 0:
                detect.car_run()
                load_opencv = 1
    except:
        pass
    
    capture.release()
    detect.cancel()
    cv.destroyAllWindows()
    
