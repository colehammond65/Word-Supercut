#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
import tempfile
import re
import shutil
import signal
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# -------------------- yt-dlp Silent Logger --------------------
class QuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

# -------------------- Virtualenv Setup --------------------
def create_venv(venv_path: Path):
    import venv
    python_bin = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    pip_bin = venv_path / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")

    if sys.prefix == str(venv_path.resolve()):
        return

    required = ["faster_whisper", "ffmpeg-python", "tqdm", "yt-dlp", "rapidfuzz", "rich"]

    if not venv_path.exists():
        print(f"[*] Creating high-quality environment in {venv_path}...")
        venv.create(venv_path, with_pip=True)
        subprocess.check_call([str(pip_bin), "install", "-U", "pip"], stdout=subprocess.DEVNULL)
        subprocess.check_call([str(pip_bin), "install"] + required, stdout=subprocess.DEVNULL)

    os.execv(str(python_bin), [str(python_bin)] + sys.argv)

# -------------------- Main Logic --------------------
def main():
    import ffmpeg
    from yt_dlp import YoutubeDL
    from faster_whisper import WhisperModel
    from tqdm import tqdm
    from rapidfuzz import fuzz
    from rich.console import Console
    from rich.table import Table

    console = Console()

    parser = argparse.ArgumentParser(description="High-Quality AI Supercut Tool")
    parser.add_argument("video", help="URL or local path")
    parser.add_argument("output", help="Output path")
    parser.add_argument("--word", required=True, help="Word to find")
    parser.add_argument("--before", type=float, default=0.5)
    parser.add_argument("--after", type=float, default=0.5)
    parser.add_argument("--model", default="medium")
    parser.add_argument("--threads", type=int, default=os.cpu_count())
    parser.add_argument("--debug", action="store_true", help="Show all logs/warnings")
    args = parser.parse_args()

    # Hardware Detection & High-Quality Encoding Params
    try:
        subprocess.check_output(['nvidia-smi'], stderr=subprocess.STDOUT)
        device, compute_type = "cuda", "float16"
        # NVENC HQ Settings: Variable Bitrate, CQ 19, Slow Preset
        enc_params = {"vcodec": "h264_nvenc", "rc": "vbr", "cq": "19", "preset": "slow"}
        console.print("[bold green]✔ NVIDIA GPU Detected.[/bold green] Using HQ Hardware Encoding.")
    except:
        device, compute_type = "cpu", "int8"
        # CPU HQ Settings: CRF 18 (Visually Lossless), Slow Preset
        enc_params = {"vcodec": "libx264", "crf": "18", "preset": "slow"}
        console.print("[yellow]! No GPU detected.[/yellow] Using HQ CPU Encoding (Slow but High Quality).")

    def cleanup(sig, frame):
        console.print("\n[bold red]✖ Interrupted. Cleaning up...[/bold red]")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Download
        video_file = args.video
        if args.video.startswith(("http", "www")):
            console.print("[bold blue][*] Downloading Video...[/bold blue]")
            ydl_opts = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": f"{tmp_dir}/in.%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "logger": QuietLogger() if not args.debug else None
            }
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(args.video)
                video_file = ydl.prepare_filename(info)

        # 2. Transcribe
        model = WhisperModel(args.model, device=device, compute_type=compute_type)
        segments, info = model.transcribe(video_file, word_timestamps=True)

        matches = []
        target = args.word.lower()

        with tqdm(total=round(info.duration), unit="s", desc="[*] Analyzing Audio", disable=args.debug) as pbar:
            last_t = 0
            for seg in segments:
                if seg.words:
                    for w in seg.words:
                        clean = re.sub(r'[^\w]', '', w.word).lower()
                        if fuzz.ratio(clean, target) > 85:
                            matches.append((max(0, w.start - args.before), min(info.duration, w.end + args.after)))
                pbar.update(seg.end - last_t)
                last_t = seg.end

        if not matches:
            console.print(f"[bold red]No occurrences of '{args.word}' found.[/bold red]")
            return

        # 3. Merge Intervals
        matches.sort()
        merged = []
        if matches:
            curr_s, curr_e = matches[0]
            for next_s, next_e in matches[1:]:
                if next_s <= curr_e: curr_e = max(curr_e, next_e)
                else:
                    merged.append((curr_s, curr_e))
                    curr_s, curr_e = next_s, next_e
            merged.append((curr_s, curr_e))

        # Pretty Table
        table = Table(title=f"Matches for '{args.word}'")
        table.add_column("Match #", justify="right", style="cyan")
        table.add_column("Timestamp", style="magenta")
        table.add_column("Duration", justify="right")
        for i, (s, e) in enumerate(merged):
            table.add_row(str(i+1), f"{s:.2f}s - {e:.2f}s", f"{e-s:.2f}s")
        console.print(table)

        # 4. Parallel Cutting (HQ Re-encoding)
        def cut_segment(data):
            idx, start, end = data
            out = os.path.join(tmp_dir, f"clip_{idx}.mp4")
            try:
                (
                    ffmpeg.input(video_file, ss=start, to=end)
                    .output(out, acodec="aac", pix_fmt="yuv420p", loglevel="error" if not args.debug else "info", **enc_params)
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
                return out
            except: return None

        console.print(f"[bold blue][*] Cutting {len(merged)} clips in High Quality...[/bold blue]")
        tasks = [(i, m[0], m[1]) for i, m in enumerate(merged)]
        with ThreadPoolExecutor(max_workers=args.threads) as exec:
            clips = list(tqdm(exec.map(cut_segment, tasks), total=len(tasks), desc="[*] Rendering Clips", disable=args.debug))

        # 5. Final Concat
        clips = [c for c in clips if c]
        list_file = os.path.join(tmp_dir, "list.txt")
        with open(list_file, "w") as f:
            for c in clips: f.write(f"file '{os.path.abspath(c)}'\n")

        console.print("[bold blue][*] Merging Final Supercut...[/bold blue]")
        (
            ffmpeg.input(list_file, format="concat", safe=0)
            .output(args.output, c="copy", loglevel="error" if not args.debug else "info")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )

        console.print(f"\n[bold green]✔ SUCCESS![/bold green] High-quality supercut saved to: [bold underline]{args.output}[/bold underline]")

if __name__ == "__main__":
    VENV_PATH = Path("./wow_env")
    if not shutil.which("ffmpeg"):
        print("[!] FFmpeg not found. Please install it first.")
        sys.exit(1)
    create_venv(VENV_PATH)
    main()
