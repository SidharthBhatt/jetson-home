import sounddevice as sd
import scipy.io.wavfile as wav
import subprocess
import os
from datetime import datetime

DURATION = 10
SAMPLE_RATE = 44100
#ENSURE IN SETTINGS INPUT DEVICE IS Microphone - ORBBEC Depth Sensor (with the mic emoji)
#terminal 1
# cd sidharth_dev/record_audio
# python3 record_audio.py
time_now = datetime.now()
print("Recording for 10 seconds...")
audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
sd.wait()
print("Done. Saving...")

wav.write("output.wav", SAMPLE_RATE, audio)
subprocess.run(["ffmpeg", "-y", "-i", "output.wav", f"output{time_now}.mp3"], check=True, capture_output=True)
os.remove("output.wav")
print("Saved as output m3 file")
