import os
import subprocess
import PySimpleGUI as sg
import pyttsx3
from PIL import Image
import sys

# Set default directory
DEFAULT_DIRECTORY = "C:/GeneratedVideos"

# Initialize TTS engine
engine = pyttsx3.init()

# Get the base directory of the script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Function to select directory or use default
def get_target_directory():
    layout = [
        [sg.Text("Choose a target directory or type 'Default':")],
        [sg.InputText(), sg.FolderBrowse()],
        [sg.Submit(), sg.Cancel()],
    ]
    window = sg.Window("Select Target Directory", layout)
    event, values = window.read()
    window.close()

    if event == "Submit":
        directory = values[0]
        if directory.lower() == "default" or directory == "":
            return DEFAULT_DIRECTORY
        return directory
    return None

# Function to get available voices from pyttsx3
def get_available_voices():
    voices = engine.getProperty('voices')
    voice_dict = {voice.name: voice.id for voice in voices}
    return voice_dict

# Function to convert script text to audio using pyttsx3
def generate_audio(script_file, selected_voice_id, output_audio):
    with open(script_file, "r", encoding='utf-8') as f:
        script = f.read()
    if selected_voice_id:
        engine.setProperty('voice', selected_voice_id)
    # Save the audio to a file
    engine.save_to_file(script, output_audio)
    engine.runAndWait()

# Function to sync lips using Wav2Lip
def generate_lip_sync(host_image, audio_file, output_video):
    # Ensure all paths are absolute
    host_image = os.path.abspath(host_image)
    audio_file = os.path.abspath(audio_file)
    output_video = os.path.abspath(output_video)
    # Use relative paths to find the Wav2Lip script and checkpoint
    wav2lip_path = os.path.join(BASE_DIR, 'Wav2Lip', 'inference.py')
    checkpoint_path = os.path.join(BASE_DIR, 'wav2lip_gan.pth')

    if not os.path.exists(host_image):
        raise FileNotFoundError(f"Host image not found: {host_image}")
    if not os.path.exists(audio_file):
        raise FileNotFoundError(f"Audio file not found: {audio_file}")
    if not os.path.exists(wav2lip_path):
        raise FileNotFoundError(f"Wav2Lip inference script not found: {wav2lip_path}")
    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Wav2Lip checkpoint file not found: {checkpoint_path}")

    command = [
        sys.executable, wav2lip_path,
        '--checkpoint_path', checkpoint_path,
        '--face', host_image,
        '--audio', audio_file,
        '--outfile', output_video
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print("Wav2Lip Error:", result.stderr)
        raise Exception(f"Wav2Lip inference failed: {result.stderr}")
    else:
        print("Wav2Lip Output:", result.stdout)

# Function to assemble the final video with background
def add_background_video(background_img, lip_synced_video, output_video):
    # Ensure all paths are absolute
    background_img = os.path.abspath(background_img)
    lip_synced_video = os.path.abspath(lip_synced_video)
    output_video = os.path.abspath(output_video)
    temp_video = os.path.join(os.path.dirname(output_video), "temp.mp4")

    if not os.path.exists(background_img):
        raise FileNotFoundError(f"Background image not found: {background_img}")
    if not os.path.exists(lip_synced_video):
        raise FileNotFoundError(f"Lip-synced video not found: {lip_synced_video}")

    # Convert background image to video
    cmd1 = [
        'ffmpeg', '-y', '-loop', '1', '-i', background_img, '-c:v', 'libx264',
        '-t', '5', '-pix_fmt', 'yuv420p', temp_video
    ]
    result1 = subprocess.run(cmd1, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result1.returncode != 0:
        print("FFmpeg Error (Background Video):", result1.stderr)
        raise Exception(f"FFmpeg failed to create background video: {result1.stderr}")

    # Overlay lip-synced video on the background
    cmd2 = [
        'ffmpeg', '-y', '-i', temp_video, '-i', lip_synced_video, '-filter_complex',
        '[0:v][1:v] overlay=0:0', '-pix_fmt', 'yuv420p', output_video
    ]
    result2 = subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result2.returncode != 0:
        print("FFmpeg Error (Overlay):", result2.stderr)
        raise Exception(f"FFmpeg failed to overlay videos: {result2.stderr}")

    os.remove(temp_video)

# Main function to gather inputs and generate the video
def main():
    # Step 1: Host Image Input
    host_image = sg.popup_get_file("Select the host image (PNG format)", file_types=(("PNG Files", "*.png"),))
    if not host_image:
        sg.popup("No host image selected. Operation cancelled.")
        return
    host_image = os.path.abspath(host_image)

    # Step 2: Host Gender Input (Optional)
    gender = sg.popup_get_text("Enter the host's gender (Male/Female):")

    # Step 3: Select Voice from pyttsx3
    voice_dict = get_available_voices()
    voice_names = list(voice_dict.keys())
    selected_voice_name = sg.popup_get_text(
        "Select a voice from the following options (type the exact name):\n" + "\n".join(voice_names)
    )
    if selected_voice_name in voice_dict:
        selected_voice_id = voice_dict[selected_voice_name]
    else:
        sg.popup("Invalid voice selected. Using default voice.")
        selected_voice_id = None  # Use default voice

    # Step 4: Script Input
    script_file = sg.popup_get_file("Select the script file (.txt)", file_types=(("Text Files", "*.txt"),))
    if not script_file:
        sg.popup("No script file selected. Operation cancelled.")
        return
    script_file = os.path.abspath(script_file)

    # Step 5: Background Image Input
    background_image = sg.popup_get_file(
        "Select the background image (PNG/JPG)",
        file_types=(("Image Files", "*.png;*.jpg;*.jpeg"),)
    )
    if not background_image:
        sg.popup("No background image selected. Operation cancelled.")
        return
    background_image = os.path.abspath(background_image)

    # Step 6: Target Directory Selection
    target_directory = get_target_directory()
    if not target_directory:
        sg.popup("Operation cancelled.")
        return
    target_directory = os.path.abspath(target_directory)

    # Step 7: Generate Output Files
    os.makedirs(target_directory, exist_ok=True)
    audio_file = os.path.join(target_directory, "audio.wav")
    lip_synced_video = os.path.join(target_directory, "lip_sync.mp4")
    final_video = os.path.join(target_directory, "final_video.mp4")

    # Generate Audio from Script
    sg.popup("Generating audio from script. This may take a moment.")
    generate_audio(script_file, selected_voice_id, audio_file)

    # Generate Lip Synced Video
    sg.popup("Generating lip-synced video. This may take a while.")
    try:
        generate_lip_sync(host_image, audio_file, lip_synced_video)
    except Exception as e:
        sg.popup(f"Error generating lip-synced video:\n{e}")
        return

    # Assemble Final Video with Background
    sg.popup("Adding background to the video.")
    try:
        add_background_video(background_image, lip_synced_video, final_video)
    except Exception as e:
        sg.popup(f"Error adding background to video:\n{e}")
        return

    sg.popup(f"Video generation complete!\nSaved at: {final_video}")

# Run the main function
if __name__ == "__main__":
    main()
