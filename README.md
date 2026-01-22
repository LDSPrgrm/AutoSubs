# AutoSubs 🎬

**AutoSubs** is a powerful, AI-driven web application designed to generate, time, and edit subtitles with precision. Built for creators who need pixel-perfect timing for music videos, anime, and Japanese content.

> **New in v2.0**: Completely redesigned Dashboard UI, Smart "Magic Wand" Timing, Undo System, and Project Management!

![AutoSubs UI Concept](https://via.placeholder.com/800x450?text=AutoSubs+Dashboard+Preview)

## ✨ Key Features

### 🧠 Smart AI Processing
- **Auto-Transcription**: Powered by `faster-whisper` (Kotoba-Whisper v1.0) for state-of-the-art Japanese recognition.
- **Auto-Translation**: Optional Japanese → English translation.
- **Energy-Based Timing**: Analyzes audio waveforms to align lyrics perfectly with vocals, even when AI transcription struggles.
- **Demucs Vocals Separation**: Automatically separates vocals from background music to make transcription 10x more accurate.

### 🎛️ Professional Editor Dashboard
- **Timeline Cards**: A clean, card-based interface for every subtitle segment.
- **"Good" Status Locking**: Mark segments as "Good" (✅) to lock them. Locked segments become read-only to prevent accidental edits.
- **Smart Snap (Magic Wand ✨)**: Messed up a segment? One click snaps it back to the nearest raw AI timestamp.
- **Gapless Editing**: Use the **Snap-to-Previous** button (`|<`) to instantly align a segment's start time with the previous segment's end time.
- **Merge & Split**: Easily merge fragmented lines or delete unwanted ones.

### 🛡️ Safety & Workflow
- **Global Undo System**: Made a mistake? A floating "Undo" notification lets you revert any action (Timing, Text, Delete, Merge).
- **Project Save/Load**: Save your work as a `.json` project file and resume later exactly where you left off.
- **Update Text Only**: Have perfect timing but want to change the lyrics? Use the "Update Text Only" feature to swap the text while keeping your locked timestamps intact.

## 🚀 Installation

### Prerequisites
- **Node.js** (v16+)
- **Python 3.11+** (Recommend using Conda)
- **FFmpeg** (Must be in your system PATH)
- **CUDA GPU** (Recommended for faster AI processing)

### 1. Backend Setup
```bash
# Create a virtual environment
conda create -n AutoSubs python=3.11 -y
conda activate AutoSubs

# Install dependencies
pip install -r backend/requirements.txt
```

### 2. Frontend Setup
```bash
cd AutoSubs
npm install
```

## ▶️ Usage Guide

### Starting the App
1. **Start the API**:
   ```bash
   cd backend
   uvicorn main:app --reload
   ```
2. **Start the UI**:
   ```bash
   # In a new terminal
   npm run dev
   ```
3. Open `http://localhost:5173`.

### Workflow
1. **Select Source**: Paste a **YouTube URL** or **Upload** a generic video/audio file.
2. **Choose Mode**:
   - **Transcribe**: Let AI listen and write the subtitles.
   - **Custom Script**: Paste your own lyrics (JP/Romaji/EN) and let the AI *synchronize* them to the audio.
3. **Edit & Refine**:
   - Use the **Timeline** to adjust start/end times.
   - Click the **Checkmark** on a card to lock it as "Done".
   - Use the **Magic Wand** if a timestamp looks wrong.
   - Use **Snap-to-Previous** to close gaps between lines.
4. **Export**: Click **Export .SRT** to download your final subtitle file.

### "Update Text Only" Workflow
*Perfect for when you've timed a song but realized you made a typo or want to add a translation later.*
1. Load your existing project (or keep it open).
2. Open the **Sidebar** and toggle **Custom Transcript**.
3. Paste the *new* text (e.g., with added English lines).
4. Click the purple **Update Text Only** button in the sidebar.
5. Your timestamps remain untouched, but the text is instantly updated!

## 📝 Script Format Examples

You can paste lyrics/scripts in blocks separated by empty lines. The app supports 2-line or 3-line formats.

**Example (Japanese + Romaji + English):**
```text
は あ～
ha a~
Ah…

たーみなるは ごちゃついてて
TAAMINARU wa gochatsuitete
The terminal is crowded and noisy

かぞくづれをみては ためいき
kazokuzure o mite wa tameiki
I watch families pass by and let out a sigh
```

**Example (Japanese + Romaji):**
```text
わたし ひとり のる ひこうきは
watashi hitori noru hikouki wa

なんこのゆめ はこぶのだろう
nanko no yume hakobu no darou
```

## 🏗️ Technology Stack
- **Frontend**: Vue 3, Vuetify 3, Vite
- **Backend**: FastAPI, Python
- **AI Models**: Faster-Whisper, Demucs (Audio Separation)
- **Tools**: yt-dlp, ffmpeg, librosa

## 📝 License
MIT License. Feel free to fork and modify!
