'''
Interface between the audio recording module and the rest of the system. 
This module is responsible for checking the audio input from the microphone and 
ensuring that it is functioning correctly. It provides functions to check the status of the audio input by doing a USB descriptor scan and the way it did it from the sensor_health.py file.
Have an audio class that has methods for each check. It should list all the audio devices connected to the system and check if the microphone is present. It should also check if the microphone
 is working by recording a short audio clip and checking if it is not silent. If the microphone is not present or not working, it should raise an exception and return a status code. 

'''


