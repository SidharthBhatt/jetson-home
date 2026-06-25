#!/bin/bash
xhost +
docker run -it \
--net=host \
--env="DISPLAY" \
--env="QT_X11_NO_MITSHM=1" \
--env="NO_AT_BRIDGE=1" \
-v /tmp/.X11-unix:/tmp/.X11-unix \
-v /home/jetson/temp:/root/temp \
-v /dev/bus/usb/001/012:/dev/bus/usb/001/012 \
-v /dev/bus/usb/001/014:/dev/bus/usb/001/014 \
--device=/dev/astro_pro_plus \
--device=/dev/astro_pro_plus_rgb \
--device=/dev/myserial \
--device=/dev/input \
-p 9090:9090 \
-p 8888:8888 \
yahboomtechnology/ros-foxy-orbslam2:1.0.0 /bin/bash
