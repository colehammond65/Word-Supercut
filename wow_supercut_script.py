#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import importlib.util

# -------------------- Virtualenv Setup --------------------
def create_venv(venv_path: Path, debug=False):
    import venv

    python_bin = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    pip_bin = venv_path / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")

    # Check if venv exists and dependencies are installed
    all_installed = True
    required_packages = [
        "faster_whisper", "ffmpeg-python", "tqdm", "yt-dlp",
        "rapidfuzz", "av", "ctranslate2", "huggingface-hub"
    ]
    for pkg in required_packages:
        if importlib.util.find_spec(pkg) is None:
            all_installed = False
            break

    if venv_path.exists() and all_installed:
        return  # Dependencies already installed

    if not venv_path.exists():
        print("[*] Creating virtual environment...")
        venv.create(venv_path, with_pip=True)

    # Upgrade pip
    print("[*] Upgrading pip...")
    pip_cmd = [str(pip_bin), "install", "--upgrade", "pip"]
    if not debug:
        pip_cmd.append("--quiet")
    subprocess.check_call(pip_cmd)

    # Install dependencies
    print("[*] Installing dependencies...")
    pip_cmd = [str(pip_bin), "install"] + required_packages
    if not debug:
        pip_cmd.append("--quiet")
    subprocess.check_call(pip_cmd)

    # Relaunch inside venv only if not already running inside it
    if sys.prefix != str(venv_path):
        print("[*] Relaunching inside virtual environment...")
        os.execv(str(python_bin), [str(python_bin)] + sys.argv)

# -------------------- Main --------------------
DEBUG_MODE = "--debug" in sys.argv
create_venv(Path("./wow_env"), debug=DEBUG_MODE)

# -------------------- Imports after venv --------------------
import ffmpeg
from yt_dlp import YoutubeDL
from faster_whisper import WhisperModel
from tqdm import tqdm
from rapidfuzz import fuzz

# -------------------- Argument Parsing --------------------
parser = argparse.ArgumentParser(description="Supercut videos based on word matches")
parser.add_argument("video", help="YouTube URL or local video file")
parser.add_argument("output", help="Output video file path")
parser.add_argument("--word", required=True, help="Word to detect in audio")
parser.add_argument("--before", type=float, default=1, help="Seconds before word to include")
parser.add_argument("--after", type=float, default=1, help="Seconds after word to include")
parser.add_argument("--model", default="medium", help="Whisper model size")
parser.add_argument("--device", default="cpu", choices=["cpu","cuda"], help="Device for transcription")
parser.add_argument("--debug", action="store_true", help="Show full logs")
args = parser.parse_args()

LOGLEVEL = "info" if args.debug else "quiet"

# -------------------- YouTube Download --------------------
def download_video(url):
    if os.path.exists(url):
        return url
    print("[*] Downloading video...")
    ydl_opts = {
        "format": "best",
        "quiet": not args.debug,
        "outtmpl": "downloaded_video.%(ext)s"
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url)
        return ydl.prepare_filename(info)

# -------------------- Audio Extraction --------------------
def extract_audio(video_path):
    tmp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_audio_path = tmp_audio.name
    tmp_audio.close()
    try:
        (
            ffmpeg.input(video_path)
            .output(tmp_audio_path, ac=1, ar=16000, vn=True, loglevel=LOGLEVEL)
            .overwrite_output()
            .run()
        )
    except ffmpeg.Error as e:
        print("[!] FFmpeg audio extraction failed.")
        if args.debug:
            print(e.stderr.decode() if e.stderr else e)
        sys.exit(1)
    return tmp_audio_path

# -------------------- Transcription and Word Detection --------------------
def transcribe_and_find_matches(audio_path):
    print("[*] Transcribing audio...")
    model = WhisperModel(args.model, device=args.device)
    segments, _ = model.transcribe(audio_path, beam_size=5)
    matches = []
    for seg in segments:
        words = getattr(seg, "words", [])
        for word in words:
            if fuzz.ratio(word.word.lower(), args.word.lower()) > 80:
                start = max(0, word.start - args.before)
                end = word.end + args.after
                matches.append((start, end))
    return matches

# -------------------- Video Cutting --------------------
def cut_video(video_path, output_file, matches):
    if not matches:
        print("[*] No matches found. Exiting.")
        sys.exit(0)

    print(f"[*] Cutting {len(matches)} segments...")
    inputs = []
    for i, (start, end) in enumerate(tqdm(matches, desc="Trimming clips")):
        tmp_out = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_out_path = tmp_out.name
        tmp_out.close()
        try:
            (
                ffmpeg.input(video_path, ss=start, to=end)
                .output(tmp_out_path, c="copy", loglevel=LOGLEVEL)
                .overwrite_output()
                .run()
            )
        except ffmpeg.Error as e:
            print(f"[!] Failed to trim segment {i}")
            if args.debug:
                print(e.stderr.decode() if e.stderr else e)
            continue
        inputs.append(tmp_out_path)

    if not inputs:
        print("[!] No clips created. Exiting.")
        sys.exit(1)

    # Concatenate clips
    concat_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    for clip in inputs:
        concat_file.write(f"file '{os.path.abspath(clip)}'\n")
    concat_file.flush()
    concat_file_path = concat_file.name
    concat_file.close()

    print("[*] Merging clips...")
    try:
        (
            ffmpeg.input(concat_file_path, format="concat", safe=0)
            .output(output_file, c="copy", loglevel=LOGLEVEL)
            .overwrite_output()
            .run()
        )
    except ffmpeg.Error as e:
        print("[!] Failed to merge clips.")
        if args.debug:
            print(e.stderr.decode() if e.stderr else e)
        sys.exit(1)

    print(f"[*] Supercut saved to {output_file}")

# -------------------- Main --------------------
video_file = download_video(args.video)
audio_file = extract_audio(video_file)
matches = transcribe_and_find_matches(audio_file)
cut_video(video_file, args.output, matches)

# Cleanup
os.unlink(audio_file)
