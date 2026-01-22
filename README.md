<div align="center">

# 🎬 AutoSubs
### AI-Powered Subtitle Creation & Editing Studio

![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Frontend](https://img.shields.io/badge/Frontend-Vue_3-4FC08D?style=for-the-badge&logo=vue.js&logoColor=white)
![Backend](https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![AI](https://img.shields.io/badge/AI-Faster_Whisper-4B32C3?style=for-the-badge)
![Acceleration](https://img.shields.io/badge/Acceleration-CUDA-76B900?style=for-the-badge&logo=nvidia&logoColor=white)

</div>

## ✨ Overview
**AutoSubs** is a professional-grade web application designed to generate, time, and edit subtitles for music videos and Japanese content. Unlike basic subtitle generators, AutoSubs provides a full-featured **Non-Linear Editor (NLE)** interface for pixel-perfect timing adjustments.

It combines state-of-the-art AI (**Kotoba-Whisper v2.0**) with a modern **Vue 3** dashboard to give you complete control over your subtitles.

> **New in v2.0**: Integrated Vocals Player, 4K Video Downloader, and Smart "Magic Wand" Timing!

---

## ⚡ Core Features

| Feature | Description |
| :--- | :--- |
| **🧠 Smart Transcription** | Powered by `Kotoba-Whisper` for high-accuracy Japanese recognition, even with background music. |
| **🎼 Vocals Separation** | Automatically isolates vocals using **Demucs** to ensure the AI listens to the singer, not the drums. |
| **🎛️ Pro Editor** | A drag-and-drop timeline with locking, merging, and "Magic Wand" smart snapping. |
| **⚡ Smart Scrolling** | The editor automatically follows playback, keeping your active segment in focus. |
| **🛡️ Global Undo** | Mistake-proof editing with a floating "Undo" notification for every action. |
| **📥 4K Downloader** | Built-in tool to fetch the highest quality video (up to 4K) from YouTube automatically. |
| **📝 Text-Only Update** | Swap lyrics without losing your perfect timing alignment. |

## 🛠️ System Requirements
Before setup, ensure you meet the following prerequisites:

*   **OS**: Windows 10/11
*   **Runtime**: Node.js (v16+) and Python 3.11+
*   **GPU**: NVIDIA GPU with CUDA (Highly Recommended for AI performance)
*   **Tools**: `ffmpeg` must be installed and in your system PATH.

## 📦 Installation Guide

We recommend using **Conda** to manage the Python environment to avoid conflict with system libraries.

### 1. Initialize Backend
Create the environment and install the AI engine.

```bash
# Create environment
conda create -n AutoSubs python=3.11 -y
conda activate AutoSubs

# Install Python dependencies
pip install -r backend/requirements.txt
```

### 2. Initialize Frontend
Install the Vue 3 web interface dependencies.

```bash
cd AutoSubs // If not already in root
npm install
```

## 🎮 Controls & Usage

### Start the Studio
You need two terminals running simultaneously.

**Terminal 1 (API):**
```bash
cd backend
uvicorn main:app --reload
```

**Terminal 2 (UI):**
```bash
npm run dev
```
> Access the dashboard at: `http://localhost:5173`

### Workflow Map

| Action | Effect |
| :--- | :--- |
| **Transcribe** | Enter a YouTube URL and let the AI generate subtitles from scratch. |
| **Custom Script** | Paste precise lyrics (JP/Romaji/EN) and let the AI **synchronize** them to the audio. |
| **Magic Wand ✨** | Click to snap a segment's timing to the nearest raw AI timestamp. |
| **Snap `<|`** | Instantly align a segment's start to the previous segment's end (Gapless). |
| **Lock ✅** | Mark a segment as "Good" to prevent accidental edits. |

## ⚙️ Configuration

The backend is configured via `backend/main.py`. Key logic includes:

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Whisper Model** | `kotoba-tech/kotoba-whisper-v2.0-faster` | Optimized for Japanese speech. |
| **Quantization** | `float16` (GPU) / `int8` (CPU) | Auto-switches based on hardware availability. |
| **Vocals** | `Demucs (htdemucs)` | Separates stems to improve transcription accuracy. |

## ❓ Troubleshooting

**Q: "The AI output is gibberish on music videos."**
A: Ensure **Vocals Separation** is enabled (or happens automatically in Custom Script mode). Drums and guitars confuse the AI.

**Q: "Download fails."**
A: Start the specific download tool or check `yt-dlp` updates.

---
*Built with ❤️ for Anime & POV Creators.*
