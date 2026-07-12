import argparse
import os
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv
import sys
import json

def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise SystemExit("Error: FFmpeg is not available on your PATH. Please install FFmpeg to use this script.")

def load_workspace_voice_id(prepared_voice_path):
    if not Path(prepared_voice_path).is_file():
        raise SystemExit(f"Error: Prepared voice JSON file not found: {prepared_voice_path}")
    try:
        with open(prepared_voice_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        workspace_voice_id = data.get("workspace_voice_id")
        if not workspace_voice_id:
            raise ValueError
        return workspace_voice_id
    except Exception:
        raise SystemExit(f"Error: Could not extract 'workspace_voice_id' from {prepared_voice_path}. Ensure the JSON has this field.")

def extract_audio(input_video, temp_audio_path):
    cmd = [
        'ffmpeg',
        '-y',
        '-i', input_video,
        '-vn',
        '-acodec', 'libmp3lame',
        '-ar', '44100',
        '-q:a', '2',
        temp_audio_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as e:
        raise SystemExit(f"Error extracting audio from video '{input_video}'. FFmpeg said:\n{e.stderr.decode(errors='ignore')}")

def send_to_elevenlabs_sts(source_audio_path, voice_id, api_key, model_id, out_path):
    url = f"https://api.elevenlabs.io/v1/speech-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg"
    }
    files = {
        'audio': ('source_audio.mp3', open(source_audio_path, 'rb'), 'audio/mpeg')
    }
    data = {
        "model_id": model_id
    }
    try:
        response = requests.post(url, headers=headers, data=data, files=files, timeout=180)
        files['audio'][1].close()
    except Exception as e:
        raise SystemExit(f"Error communicating with ElevenLabs API: {e}")
    if response.status_code != 200 or not response.content:
        raise SystemExit(
            f"Error: ElevenLabs API returned status {response.status_code}.\n"
            f"Message: {getattr(response, 'text', '(no text)')}\n"
        )
    try:
        with open(out_path, 'wb') as f:
            f.write(response.content)
    except Exception as e:
        raise SystemExit(f"Error writing output audio to '{out_path}': {e}")

def get_video_duration(input_video):
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'json',
        input_video
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        info = json.loads(result.stdout)
        duration = float(info['format']['duration'])
        return duration
    except Exception:
        return None

def main():
    load_dotenv()
    api_key = os.environ.get('ELEVENLABS_API_KEY')
    if not api_key or not api_key.strip():
        raise SystemExit("Error: ELEVENLABS_API_KEY not found in environment. Please set it in your .env file or environment variables.")

    parser = argparse.ArgumentParser(
        description="Extracts audio from a video and sends to ElevenLabs Speech-to-Speech (STS) for conversion."
    )
    parser.add_argument('--video', default='cloudtechuk.mp4', help='Input video file (default: cloudtechuk.mp4)')
    parser.add_argument('--prepared-voice', default='prepared_voice.json', help='JSON file containing workspace_voice_id')
    parser.add_argument('--out', default='output.mp3', help='Output mp3 filename (default: output.mp3)')
    parser.add_argument('--model', default='eleven_multilingual_sts_v2', help='ElevenLabs STS model ID')
    parser.add_argument('--keep-temp', action='store_true', help='Keep the extracted temp audio for inspection')

    args = parser.parse_args()

    input_video = args.video
    prepared_voice_path = args.prepared_voice
    output_path = args.out
    model_id = args.model
    keep_temp = args.keep_temp

    temp_audio_path = "source_audio.mp3"

    if not Path(input_video).is_file():
        raise SystemExit(f"Error: Input video file not found: {input_video}")

    # Step 1: Check FFmpeg
    check_ffmpeg()

    # Step 2: Load prepared voice JSON
    workspace_voice_id = load_workspace_voice_id(prepared_voice_path)

    # Step 3: Extract audio to temp file
    extract_audio(input_video, temp_audio_path)

    # Step 4 & 5: Send to ElevenLabs, save output
    send_to_elevenlabs_sts(temp_audio_path, workspace_voice_id, api_key, model_id, output_path)

    # Step 6: Delete temp unless --keep-temp set
    if not keep_temp and Path(temp_audio_path).exists():
        try:
            os.remove(temp_audio_path)
        except Exception as e:
            print(f"Warning: Could not remove temp file {temp_audio_path}: {e}", file=sys.stderr)

    # Print summary
    duration = get_video_duration(input_video)
    try:
        out_size = Path(output_path).stat().st_size
    except Exception:
        out_size = 'unknown'

    print("\n--- Speech-to-Speech Pipeline Complete ---")
    print(f"Input video:         {input_video}")
    print(f"Video duration:      {duration:.2f} sec" if duration else "Video duration:      (could not determine)")
    print(f"Prepared voice ID:   {workspace_voice_id}")
    print(f"STS model used:      {model_id}")
    print(f"Output file:         {output_path}")
    print(f"Output file size:    {out_size} bytes" if isinstance(out_size, int) else f"Output file size:    unknown")

if __name__ == "__main__":
    main()