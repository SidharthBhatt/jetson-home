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
from audio_common_msgs.msg import AudioData
import numpy as np



# Laptop Terminal 
'''
cd ~/sidharth_dev/audio_record
python3 microphone_publisher.py --ros-args -p mode:=artificial
'''
# every 10 seconds, it records audio then transcribes and publishes it to /audio/transcribed


DURATION = 10
SAMPLE_RATE = 16000

class MicrophonePublisher(Node):
    def __init__(self):
        super().__init__('microphone_publisher')
        self.declare_parameter('mode', 'real')
        mode = self.get_parameter('mode').value
        self.raw_pub = self.create_publisher(AudioData, '/audio/raw', 10)  #this 10 at the end is some garbage QOS nonsense u can ignore 
        self.txt_pub = self.create_publisher(String, '/audio/transcribed', 10)  #this 10 at the end is some garbage QOS nonsense u can ignore 
        #self.model = whisper.load_model("medium")
        timer_period = 10
        if mode == "real":
            self.timer = self.create_timer(timer_period, self.real_callback)  # every 10 seconds
        if mode == "artificial":
            self.timer = self.create_timer(timer_period, self.artificial_callback)  # every 10 seconds

    def real_callback(self):
        
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
        msg_audio = AudioData()
        msg_audio.data = audio.tobytes()
        self.raw_pub.publish(msg_audio)
       

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
        msg_txt = String()
        msg_txt.data = result.text
        self.txt_pub.publish(msg_txt)
    def artificial_callback(self):
        # mic is broken so we will use this for now 
        audio = subprocess.run(["ffmpeg", "-v", "quiet", "-i", "/home/jetson/sidharth_dev/audio_record/output2026-06-25 06:13:10.663178.mp3", "-f", "s16le", "-ac", "1", "-ar", "16000", "pipe:1"], capture_output=True)
        audio = np.frombuffer(audio.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        msg_audio = AudioData()
        msg_audio.data = audio.tobytes()
        self.raw_pub.publish(msg_audio)
        msg_txt = String()
        msg_txt.data = "This is an artificial callback message [insert audio here]"
        self.txt_pub.publish(msg_txt)


def main():
    rclpy.init()
    node = MicrophonePublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()