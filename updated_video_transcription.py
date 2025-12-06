import subprocess
import sys
import os
import json
import wave
import langdetect

# Get the base directory
base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
print(base_dir)

try:
    import tkinter
except ImportError:
    print("tkinter missing. Install Python with Tk support.")
    sys.exit(1)

from vosk import Model, KaldiRecognizer
import whisper


# -------------------------
# FORMAT TEXT
# -------------------------
def format_transcription(text):
    text = text.replace(". ", ".\n")
    text = text.replace("? ", "?\n")
    text = text.replace("! ", "!\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


# -------------------------
# VOSK TRANSCRIPTION
# -------------------------
def transcribe_vosk(audio_path, model_path):
    if not os.path.exists(model_path):
        print(f"Vosk model path not found: {model_path}")
        return ""

    model = Model(model_path)
    recognizer = KaldiRecognizer(model, 16000)
    text = ""

    with wave.open(audio_path, "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
            print("Audio must be 16KHz, mono, PCM WAV.")
            return ""

        while True:
            data = wf.readframes(4000)
            if not data:
                break

            if recognizer.AcceptWaveform(data):
                res = json.loads(recognizer.Result())
                text += res.get("text", "") + " "

        res = json.loads(recognizer.FinalResult())
        text += res.get("text", "")

    return text


# -------------------------
# WHISPER TRANSCRIPTION
# -------------------------
def transcribe_whisper(audio_path):
    try:
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        return result.get("text", "")
    except Exception as e:
        print(f"Whisper failed: {e}")
        return ""


# -------------------------
# DETECT LANGUAGE FROM TEXT
# -------------------------
def detect_language(text):
    try:
        return langdetect.detect(text)
    except:
        return "unknown"


# -------------------------
# TRANSLATE TO ENGLISH USING WHISPER
# -------------------------
def translate_to_english(audio_path):
    try:
        model = whisper.load_model("small")
        result = model.transcribe(audio_path, task="translate")
        return result.get("text", "")
    except Exception as e:
        print(f"Translation failed: {e}")
        return ""


# -------------------------
# EXTRACT AUDIO USING FFMPEG
# -------------------------
def extract_audio(video_path, output_audio_path):
    command = f'ffmpeg -i "{video_path}" -ar 16000 -ac 1 -vn "{output_audio_path}" -y'
    os.system(command)


# -------------------------
# RECURSIVE VIDEO SCAN
# -------------------------
def get_all_video_files(root_dir):
    video_files = []
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            if file.lower().endswith(('.mkv', '.mp4', '.avi', '.mov')):
                video_files.append(os.path.join(root, file))
    return video_files


# -------------------------
# MAIN PROCESSING
# -------------------------
if len(sys.argv) > 1:
    videos_dir = sys.argv[1]
else:
    videos_dir = os.path.join(base_dir, "data_files", "Database")

transcription_folder = os.path.join(videos_dir, "Transcription")
os.makedirs(transcription_folder, exist_ok=True)

vosk_model_path = r"C:\\Users\\Ashutosh Mishra\\Desktop\\STUDY\\Coding\\vosk-model-en-us-0.22"

video_files = get_all_video_files(videos_dir)
print(f"Found {len(video_files)} video files to process.\n")

for video_path in video_files:
    file_name = os.path.splitext(os.path.basename(video_path))[0]
    print(f"\n==============================")
    print(f"Processing: {file_name}")
    print("==============================")

    # Extract audio
    audio_path = os.path.join(transcription_folder, file_name + ".wav")
    extract_audio(video_path, audio_path)

    # Transcription - Whisper preferred
    transcription = transcribe_whisper(audio_path)

    # Vosk fallback
    if not transcription.strip():
        print("Whisper failed or returned empty. Using Vosk...")
        transcription = transcribe_vosk(audio_path, vosk_model_path)

    if not transcription.strip():
        print("No transcription available.")
        continue

    # Detect language
    print("Detecting language...")
    detected_lang = detect_language(transcription)
    print(f"Detected language: {detected_lang}")

    # -------------------------
    # SAVE ONLY ONE FILE
    # -------------------------

    # CASE 1: Already English → Save as <name>_transcription.txt
    if detected_lang == "en":
        output_file = os.path.join(transcription_folder, file_name + "_transcription.txt")
        final_text = transcription
        print("Language is English → saving without translation.")

    # CASE 2: Not English → Translate → Save ONLY translated file
    else:
        print("Non-English detected → translating to English...")
        final_text = translate_to_english(audio_path)
        output_file = os.path.join(transcription_folder, file_name + "_transcription_english.txt")

    # Save output
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(format_transcription(final_text))

    # Remove temp audio
    if os.path.exists(audio_path):
        os.remove(audio_path)

print("\nTranscription + Conditional English Translation complete!")
