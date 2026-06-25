#!/usr/bin/env python3
# coding: utf-8

import Speech_Lib
import time

spe = Speech_Lib.Speech()

try:
    while True:
        speech_r = spe.speech_read()
        #print(speech_r)
        if speech_r != 999:
            print(speech_r)
            time.sleep(0.1)
            spe.void_write(speech_r)
except KeyboardInterrupt:
    print("Close!")
