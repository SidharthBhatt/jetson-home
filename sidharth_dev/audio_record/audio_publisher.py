#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
import sounddevice as sd
import scipy.io.wavfile as wav
import subprocess
import os
from datetime import datetime
import whisper
from pathlib import Path
from std_msgs.msg import String
import numpy as np



# How to use
#
# every 10 seconds, it records audio then transcribes and publishes it to /audio/transcribed
DURATION = 10
SAMPLE_RATE = 16000

class AudioPublisher(Node):
    def __init__(self):
        super().__init__('audio_publisher')
        self.pub = self.create_publisher(String, '/audio/transcribed', 10)  #this 10 at the end is some garbage QOS nonsense u can ignore 
        self.model = whisper.load_model("medium")
        timer_period = 10
        self.timer = self.create_timer(timer_period, self.tick_callback)  # every 10 seconds

    def tick_callback(self):
        
        print("Recording for 10 seconds...")
        audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
        sd.wait()
        
        audio = audio.flatten().astype(np.float32) / 32768.0   # (N,1) int16 → (N,) float32 in [-1,1]
        if np.sqrt((audio ** 2).mean()) < 0.01:   # ← clip is silent: skip (decode + publish)
            return
        
        print("Done. Saving...")

        # if not ok:
        #     self.get_logger().warn('no audio')
        #     return
        audio = whisper.pad_or_trim(audio)
       

        # make log-Mel spectrogram and move to the same device as the model
        mel = whisper.log_mel_spectrogram(audio, n_mels=self.model.dims.n_mels).to(self.model.device)

        # detect the spoken language
        _, probs = self.model.detect_language(mel)
    
        # decode the audio
        options = whisper.DecodingOptions()
        result = whisper.decode(self.model, mel, options)
        if result.no_speech_prob > 0.6:
            self.get_logger().warn('no speech detected')
            return
        if result.avg_logprob < -1:
            self.get_logger().warn('low confidence')
            return
        if result.text.strip() in {"Thanks for watching!", "Thank you.", "", "Thank you for watching!", "Thanks for watching", "Thanks for watching",""}:
            self.get_logger().warn('ignored because of a known hallucination phrase')
            return
        if result.compression_ratio > 2.4:
            self.get_logger().warn('repeated hallucinations')
            return
        msg = String()
        msg.data = result.text
        self.pub.publish(msg)

def main():
    rclpy.init()
    node = AudioPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()