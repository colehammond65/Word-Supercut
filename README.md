# 🎥 AI Supercut Tool

An automated video editing utility that uses AI transcription to create "supercuts" of any video based on specific words or phrases. Whether it's a 2-hour livestream or a local file, this tool finds every occurrence of a word and stitches them together into a high-quality highlight reel.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![FFmpeg](https://img.shields.io/badge/ffmpeg-required-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## ✨ Features

- **🤖 AI Powered**: Uses [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) for incredibly fast and accurate speech-to-text.
- **🌐 YouTube Integration**: Pass a YouTube URL directly; the script handles the download automatically via `yt-dlp`.
- **⚡ Parallel Processing**: Utilizes multi-core CPUs to cut video segments simultaneously, significantly reducing export times.
- **🚀 Hardware Acceleration**: Automatically detects NVIDIA GPUs (CUDA) for lightning-fast AI inference and video encoding.
- **🛠 Zero-Config Environment**: Automatically creates its own virtual environment and installs all necessary dependencies on the first run.
- **📊 Professional UI**: Clean terminal interface with progress bars, summary tables, and silent operation (hides technical warnings).
- **✂ Snappy Transitions**: Optimized for high-energy supercuts with instant transitions and overlapping interval merging.

## 📋 Prerequisites

The only manual requirement is **FFmpeg**. 

- **Windows**: `choco install ffmpeg` or download from [ffmpeg.org](https://ffmpeg.org).
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

## 🚀 Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/supercut-tool.git
   cd supercut-tool
   ```

2. **Run the script:**
   The script will automatically set up its environment on the first run.
   ```bash
   python wow_supercut_script.py "https://www.youtube.com/watch?v=example" output.mp4 --word "wow"
   ```

## ⚙ Usage

```bash
python wow_supercut_script.py <input> <output> --word <target> [options]
```

### Arguments:
| Argument | Description | Default |
| :--- | :--- | :--- |
| `video` | YouTube URL or path to a local video file | (Required) |
| `output` | Path for the final supercut video | (Required) |
| `--word` | The word or phrase to search for | (Required) |
| `--before` | Seconds of footage to include *before* the word | `0.5` |
| `--after` | Seconds of footage to include *after* the word | `0.5` |
| `--model` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`) | `small` |
| `--threads` | Number of parallel threads for video cutting | `CPU Count` |
| `--debug` | Show technical logs, FFmpeg output, and yt-dlp warnings | `False` |

## 🛠 How it Works

1. **Environment Setup**: The script checks for a local `./wow_env`. If missing, it creates it and installs `faster-whisper`, `ffmpeg-python`, `yt-dlp`, and `rich`.
2. **Acquisition**: If a URL is provided, it downloads the best quality MP4 using `yt-dlp`.
3. **Transcription**: The AI listens to the audio, generating word-level timestamps with high precision.
4. **Interval Logic**: It identifies the target words and merges overlapping timeframes (e.g., if someone says "Wow!" twice in one second, it creates one smooth clip instead of two overlapping ones).
5. **Parallel Cut**: The video is split into segments using your CPU/GPU cores in parallel.
6. **Merge**: FFmpeg concatenates the segments into a single, seamless final file.

## ⚖ License

This project is licensed under the MIT License - see the LICENSE file for details.

---
*Created with ❤️ by [colehammond65](https://github.com/colehammond65)*
