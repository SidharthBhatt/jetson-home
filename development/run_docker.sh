#!/bin/bash

xhost +

docker run -it \
--gpus all \
--runtime=nvidia \
--net=host \
--env="DISPLAY" \
--env="QT_X11_NO_MITSHM=1" \
--env="NO_AT_BRIDGE=1" \
-v /tmp/.X11-unix:/tmp/.X11-unix \
-v /home/jetson/temp:/root/temp \
-v /dev/bus/usb/001/012:/dev/bus/usb/001/012 \
-v /dev/bus/usb/001/014:/dev/bus/usb/001/014 \
--device=/dev/myserial \
--device=/dev/ydlidar \
--device=/dev/astro_pro_plus \
--device=/dev/astro_pro_plus_rgb \
--device=/dev/input \
--device=/dev/camera_usb \
--device=/dev/camera_depth \
-p 9090:9090 \
-p 8888:8888 \
yahboomtechnology/ros-noetic:3.0.5 /bin/bash
