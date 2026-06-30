import whisper
from pathlib import Path
#goes through the mp3 files and transcribes them, prints a one word token if it doesn't hear anything
#terminal 2
'''
cd ~/sidharth_dev/microphone
python3 transcribe_audio.py
'''

model = whisper.load_model("base")

# load audio and pad/trim it to fit 30 seconds
for filepath in Path('.').rglob('*.mp3'):
    print(filepath)
    audio = whisper.load_audio(filepath)
    audio = whisper.pad_or_trim(audio)

    '''
    A log-Mel spectrogram is a visual representation of an audio signal’s acoustic energy that mimics human auditory perception. It transforms raw audio waveforms into a 2D matrix (similar to a grayscale image) so that it can be efficiently processed by machine learning models like convolutional neural networks (CNNs) and Transformers.
    '''
    # make log-Mel spectrogram and move to the same device as the model
    mel = whisper.log_mel_spectrogram(audio, n_mels=model.dims.n_mels).to(model.device)

    # detect the spoken language
    _, probs = model.detect_language(mel)
    print(f"Detected language: {max(probs, key=probs.get)}")

    # decode the audio
    options = whisper.DecodingOptions()
    result = whisper.decode(model, mel, options)

    # print the recognized text
    print(result.text)

