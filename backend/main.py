import os
import shutil
import tempfile
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp
from faster_whisper import WhisperModel
import asyncio
from typing import Optional
import subprocess
import numpy as np
import librosa
import pykakasi
import re
import uuid

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

app = FastAPI()

# Ensure static directory exists
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize pykakasi for romaji conversion
kks_gen = pykakasi.kakasi()
kks_gen.setMode("H", "a")  # Hiragana to ascii
kks_gen.setMode("K", "a")  # Katakana to ascii
kks_gen.setMode("J", "a")  # Kanji to ascii
kks_gen.setMode("s", True)  # Add spaces
converter = kks_gen.getConverter()

# Global model loading
model = None

def get_model():
    global model
    if model is None:
        print("Loading Kotoba-Whisper Model...")
        model_name = "kotoba-tech/kotoba-whisper-v2.0-faster"
        
        try:
            print("Attempting to load on GPU (CUDA)...")
            model = WhisperModel(model_name, device="cuda", compute_type="float16")
            print("Model loaded on GPU.")
        except Exception as e:
            print(f"GPU Load Failed: {e}")
            print("Falling back to CPU (int8)...")
            model = WhisperModel(model_name, device="cpu", compute_type="int8")
            print("Model loaded on CPU.")
    return model


def separate_vocals_demucs(audio_path: str, output_dir: str) -> str:
    """
    Use Demucs to separate vocals from music.
    Returns path to isolated vocals.wav
    
    This is the KEY to making Whisper work on music!
    """
    import sys
    print(f"[Demucs] Separating vocals from: {audio_path}")
    sys.stdout.flush()
    
    # Run demucs command with htdemucs model (best quality/speed balance)
    # --two-stems vocals means only output vocals + other (faster)
    try:
        result = subprocess.run([
            "python", "-m", "demucs",
            "--two-stems", "vocals",
            "-n", "htdemucs",
            "-o", output_dir,
            audio_path
        ], capture_output=True, text=True, timeout=300)  # 5 min timeout
        
        if result.returncode != 0:
            print(f"[Demucs] stderr: {result.stderr}")
            raise Exception(f"Demucs failed: {result.stderr}")
        
        # Find the output vocals file
        # Demucs outputs to: output_dir/htdemucs/<input_filename>/vocals.wav
        audio_name = os.path.splitext(os.path.basename(audio_path))[0]
        vocals_path = os.path.join(output_dir, "htdemucs", audio_name, "vocals.wav")
        
        if os.path.exists(vocals_path):
            print(f"[Demucs] Vocals extracted: {vocals_path}")
            return vocals_path
        else:
            # Try alternate path structure
            for root, dirs, files in os.walk(output_dir):
                if "vocals.wav" in files:
                    vocals_path = os.path.join(root, "vocals.wav")
                    print(f"[Demucs] Vocals found at: {vocals_path}")
                    return vocals_path
            
            raise Exception(f"Vocals file not found in {output_dir}")
            
    except subprocess.TimeoutExpired:
        raise Exception("Demucs timed out after 5 minutes")
    except FileNotFoundError:
        raise Exception("Demucs not installed. Run: pip install demucs")


def detect_japanese(text: str) -> bool:
    """Check if text contains Japanese characters (hiragana, katakana, kanji)."""
    return bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text))


def detect_romaji(text: str) -> bool:
    """Check if text is mostly romaji (Latin + special chars like ~)."""
    # Remove common punctuation and check if remainder is ASCII-ish
    # Add smart quotes to the removal list
    clean = re.sub(r'[~\-\s\'\"!?,.‘’“”]', '', text)
    return clean.isascii() and len(clean) > 0


def parse_script_lines(script: str) -> list:
    """
    Parse user script into structured line groups.
    
    Supports formats:
    1. Japanese + Romaji (pairs)
    2. Japanese + Romaji + English (triplets)
    3. Just lines (auto-detect structure)
    
    Returns list of dicts: {japanese, romaji, english}
    """
    lines = [l.strip() for l in script.strip().split('\n') if l.strip()]
    
    if len(lines) == 0:
        return []
    
    # Strategy: Look at first few lines to detect pattern
    # Pattern A: Japanese, Romaji alternating
    # Pattern B: Japanese, Romaji, English triplets
    # Pattern C: Mixed/unknown (treat each line as a segment)
    
    # Check first few lines to guess format
    sample_size = min(6, len(lines))
    japanese_count = sum(1 for l in lines[:sample_size] if detect_japanese(l))
    romaji_count = sum(1 for l in lines[:sample_size] if detect_romaji(l) and not detect_japanese(l))
    
    result = []
    
    # Heuristic: If roughly half are Japanese, half romaji -> paired format
    if japanese_count >= sample_size // 3 and romaji_count >= sample_size // 3:
        # Likely paired format
        i = 0
        while i < len(lines):
            entry = {"japanese": "", "romaji": "", "english": ""}
            
            # First line should be Japanese
            if i < len(lines) and detect_japanese(lines[i]):
                entry["japanese"] = lines[i]
                i += 1
            
            # Second line should be Romaji
            if i < len(lines) and detect_romaji(lines[i]) and not detect_japanese(lines[i]):
                entry["romaji"] = lines[i]
                i += 1
            
            # Optional third line: English (only if next line isn't Japanese)
            # If we found JP and Romaji, and the NEXT line is not Japanese, assume it is English
            if i < len(lines) and entry["japanese"] and entry["romaji"]:
                if not detect_japanese(lines[i]):
                    entry["english"] = lines[i]
                    i += 1
            
            if entry["japanese"] or entry["romaji"]:
                result.append(entry)
            else:
                # Fallback: treat as single line
                if i < len(lines):
                    result.append({"japanese": lines[i], "romaji": "", "english": ""})
                    i += 1
    else:
        # Treat each line as a separate segment
        for line in lines:
            if detect_japanese(line):
                result.append({"japanese": line, "romaji": "", "english": ""})
            elif detect_romaji(line):
                result.append({"japanese": "", "romaji": line, "english": ""})
            else:
                result.append({"japanese": line, "romaji": "", "english": ""})
    
    return result



def get_common_ydl_opts() -> dict:
    """
    Get common yt-dlp options to fix playback/format issues.
    """
    return {
        'quiet': True,
        'no_warnings': True,
        # Use multiple clients for best format availability
        # Android client alone can limit DASH formats
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios', 'web'],
            }
        },
    }



def download_youtube(url: str, output_dir: str, download_video: bool = False):
    """
    Download from YouTube.
    If download_video is True, downloads video+audio at requested quality.
    Otherwise, downloads audio only.
    """
    
    if download_video:
        # VIDEO DOWNLOAD - Use clean config without restrictions
        # This matches the working example and ensures best quality
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(output_dir, 'video.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
    else:
        # AUDIO DOWNLOAD - Use common opts + audio-specific settings
        ydl_opts = get_common_ydl_opts()
        ydl_opts.update({
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(output_dir, 'audio'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        
        if download_video:
            # Find the downloaded video file
            video_path = None
            for ext in ['mp4', 'mkv', 'webm']:
                candidate = os.path.join(output_dir, f'video.{ext}')
                if os.path.exists(candidate):
                    video_path = candidate
                    break
            
            # Log video quality information
            if video_path and os.path.exists(video_path):
                file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                
                # Get actual selected format info (more accurate than top-level info)
                requested_formats = info.get('requested_formats', [])
                if requested_formats:
                    # When bestvideo+bestaudio is used, we get two formats
                    video_fmt = requested_formats[0] if len(requested_formats) > 0 else {}
                    audio_fmt = requested_formats[1] if len(requested_formats) > 1 else {}
                    
                    width = video_fmt.get('width', info.get('width', 'unknown'))
                    height = video_fmt.get('height', info.get('height', 'unknown'))
                    vcodec = video_fmt.get('vcodec', info.get('vcodec', 'unknown'))
                    acodec = audio_fmt.get('acodec', info.get('acodec', 'unknown'))
                    format_note = video_fmt.get('format_note', info.get('format', 'unknown'))
                else:
                    # Fallback to top-level info
                    width = info.get('width', 'unknown')
                    height = info.get('height', 'unknown')
                    vcodec = info.get('vcodec', 'unknown')
                    acodec = info.get('acodec', 'unknown')
                    format_note = info.get('format', 'unknown')
                
                print(f"[VIDEO DOWNLOAD] File: {os.path.basename(video_path)}")
                print(f"[VIDEO DOWNLOAD] Size: {file_size_mb:.2f} MB")
                print(f"[VIDEO DOWNLOAD] Resolution: {width}x{height}")
                print(f"[VIDEO DOWNLOAD] Quality: {format_note}")
                print(f"[VIDEO DOWNLOAD] Video Codec: {vcodec}")
                print(f"[VIDEO DOWNLOAD] Audio Codec: {acodec}")
            
            return info, video_path
        else:
            audio_path = os.path.join(output_dir, 'audio.mp3')
            return info, audio_path


def extract_audio_from_video(video_path: str, output_path: str):
    """Extract audio from video for processing."""
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "libmp3lame", "-q:a", "2",
        "-y", output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return output_path





def run_whisper_transcription(audio_path: str, task: str = "transcribe") -> tuple:
    """Run Whisper transcription on audio."""
    global model
    whisper = get_model()
    
    try:
        segments_generator, info = whisper.transcribe(
            audio_path,
            task=task,
            language="ja",
            condition_on_previous_text=False,
            word_timestamps=True,
            initial_prompt=" "
        )
        
        segments = []
        for segment in segments_generator:
            text = segment.text.strip()
            romaji = converter.do(text)
            combined = f"{text}\n{romaji}"
            
            segments.append({
                "id": segment.id,
                "start": segment.start,
                "end": segment.end,
                "text": combined,
                "words": [{"start": w.start, "end": w.end, "word": w.word} for w in segment.words] if segment.words else []
            })
        
        return segments, info
        
    except Exception as e:
        print(f"Transcription error: {e}")
        # Try CPU fallback if GPU failed
        if hasattr(whisper, 'model') and hasattr(whisper.model, 'device') and str(whisper.model.device) == "cuda":
            print("Falling back to CPU...")
            model = WhisperModel("kotoba-tech/kotoba-whisper-v2.0-faster", device="cpu", compute_type="int8")
            return run_whisper_transcription(audio_path, task)
        raise e


def find_vocal_range_fast(audio_path: str) -> tuple:
    """
    Quickly find when vocals/audio starts and ends using energy analysis.
    Much faster than Whisper (~5s vs 30s+).
    Returns (start_time, end_time, duration).
    """
    print("Fast energy analysis to find vocal range...")
    
    # Convert to WAV
    wav_path = audio_path + ".temp.wav"
    subprocess.run([
        "ffmpeg", "-i", audio_path,
        "-ac", "1", "-ar", "22050",
        "-y", wav_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    
    try:
        y, sr = librosa.load(wav_path, sr=None)
        duration = librosa.get_duration(y=y, sr=sr)
        
        # Compute energy
        frame_length = 4096  # Larger frames for faster processing
        hop_length = 2048
        energy = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
        times = librosa.frames_to_time(range(len(energy)), sr=sr, hop_length=hop_length)
        
        # Use 20th percentile as threshold (find when audio becomes "loud")
        threshold = np.percentile(energy, 20)
        is_active = energy > threshold
        
        # Find first and last active frame
        active_indices = np.where(is_active)[0]
        
        if len(active_indices) > 0:
            vocal_start = times[active_indices[0]]
            vocal_end = times[active_indices[-1]]
        else:
            # Fallback: use 5%-95% of duration
            vocal_start = duration * 0.05
            vocal_end = duration * 0.95
        
        # Add small buffer (don't start exactly at first sound)
        vocal_start = max(0, vocal_start - 0.5)
        vocal_end = min(duration, vocal_end + 0.5)
        
        print(f"Vocal range: {vocal_start:.1f}s to {vocal_end:.1f}s (duration: {duration:.1f}s)")
        return vocal_start, vocal_end, duration
        
    finally:
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def normalize_romaji(text: str) -> str:
    """Normalize romaji for comparison - lowercase, remove spaces/punctuation."""
    text = text.lower()
    text = re.sub(r'[^a-z]', '', text)
    return text





def process_with_script(audio_path: str, script: str, vocals_save_path: str = None) -> tuple:
    """
    Process audio with user-provided script.
    If vocals_save_path is provided, the separated vocals will be copied there.
    
    PRODUCTION PIPELINE:
    1. Demucs → Separate vocals from music
    2. Whisper → Transcribe clean vocals with timestamps
    3. Map user lyrics to Whisper segments
    """
    import time
    import sys
    
    def log(msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")
        sys.stdout.flush()
    
    log("Processing with user script...")
    
    # Parse the script
    script_entries = parse_script_lines(script)
    if not script_entries:
        raise ValueError("Could not parse script - no valid lines found")
    
    num_lines = len(script_entries)
    log(f"Parsed {num_lines} lyric entries")
    
    # Create temp directory for Demucs output
    demucs_dir = os.path.join(os.path.dirname(audio_path), "demucs_output")
    os.makedirs(demucs_dir, exist_ok=True)
    
    try:
        # Step 1: Separate vocals with Demucs
        log("Step 1/2: Separating vocals with Demucs...")
        start_time = time.time()
        
        try:
            vocals_path = separate_vocals_demucs(audio_path, demucs_dir)
            log(f"Vocals separated in {time.time() - start_time:.1f}s")
            
            # Save vocals if requested
            if vocals_save_path:
                log(f"Saving separated vocals to: {vocals_save_path}")
                shutil.copy2(vocals_path, vocals_save_path)
                
        except Exception as e:
            log(f"Demucs failed: {e}")
            log("Falling back to original audio...")
            vocals_path = audio_path
        
        # Step 2: Transcribe vocals with Whisper
        log("Step 2/2: Transcribing with Whisper...")
        whisper = get_model()
        start_time = time.time()
        
        segments_generator, info = whisper.transcribe(
            vocals_path,
            task="transcribe",
            language="ja",
            condition_on_previous_text=False,
            word_timestamps=False,
            beam_size=5,  # Better accuracy
        )
        
        # Collect segments
        whisper_segments = []
        for segment in segments_generator:
            text = segment.text.strip()
            if len(text) >= 1:
                whisper_segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": text,
                })
                if len(whisper_segments) % 10 == 1:
                    log(f"  Found {len(whisper_segments)} segments...")
        
        duration = info.duration if hasattr(info, 'duration') else 0
        log(f"Whisper found {len(whisper_segments)} segments in {time.time() - start_time:.1f}s")
        
    finally:
        # Cleanup Demucs output
        if os.path.exists(demucs_dir):
            shutil.rmtree(demucs_dir, ignore_errors=True)
    
    # Map user lyrics to Whisper segments using ANCHOR matching
    if len(whisper_segments) >= 1:
        log(f"Mapping {num_lines} lyrics to {len(whisper_segments)} Whisper segments...")
        
        # 1. Prepare data
        import difflib
        
        for ws in whisper_segments:
            ws["romaji"] = normalize_romaji(converter.do(ws["text"]))
            ws["matched_lyric_idx"] = -1
            
        # 2. Find ANCHORS (High confidence matches)
        # We look for matches where text similarity is high (>0.6)
        
        anchors = []  # List of (lyric_index, segment_index)
        
        for i, entry in enumerate(script_entries):
            # Try to get romaji from entry, or convert from japanese if missing
            romaji_text = entry.get("romaji", "")
            if not romaji_text and entry.get("japanese"):
                 romaji_text = converter.do(entry["japanese"])

            user_romaji = normalize_romaji(romaji_text)
            if len(user_romaji) < 5: continue  # Skip short lines for anchoring
            
            best_score = 0
            best_seg_idx = -1
            
            # Constrain search window to avoid wild jumps
            # Window moves as we progress through the song
            center_seg = int(i * len(whisper_segments) / num_lines)
            window_size = max(5, int(len(whisper_segments) * 0.2))
            start_j = max(0, center_seg - window_size)
            end_j = min(len(whisper_segments), center_seg + window_size)
            
            for j in range(start_j, end_j):
                ws = whisper_segments[j]
                if ws["matched_lyric_idx"] != -1: continue # Already matched
                
                # Use difflib for real sequence similarity (not just char count)
                score = difflib.SequenceMatcher(None, user_romaji, ws["romaji"]).ratio()
                
                if score > best_score:
                    best_score = score
                    best_seg_idx = j
            
            # If good match found, store as anchor
            if best_score > 0.6:
                # Ensure monotonic (must be after previous anchor)
                if not anchors or best_seg_idx > anchors[-1][1]:
                    anchors.append((i, best_seg_idx))
                    whisper_segments[best_seg_idx]["matched_lyric_idx"] = i
                    log(f"  ANCHOR: Lyric {i+1} ↔ Seg {best_seg_idx} (score: {best_score:.2f})")
        
        # Add virtual start/end anchors if missing
        if not anchors or anchors[0][0] > 0:
            anchors.insert(0, (0, 0)) # Start of song
        if anchors[-1][0] < num_lines - 1:
            anchors.append((num_lines - 1, len(whisper_segments) - 1)) # End of song
            
        log(f"Established {len(anchors)} matching anchors")
        
        # 3. Fill in gaps between anchors
        aligned = []
        
        for k in range(len(anchors) - 1):
            start_lyric, start_seg = anchors[k]
            end_lyric, end_seg = anchors[k+1]
            
            # Lyrics to place in this block (properties of start_lyric are set by start_seg)
            # We need to solve for: start_lyric ... (intermediate lyrics) ... end_lyric
            
            # Count how many lyrics we need to fit between these anchors
            lyrics_count = end_lyric - start_lyric
            if lyrics_count == 0: continue
            
            # Available time in this block
            # Start/End segments might be the same segment if multiple lines mapped to one
            s_time = whisper_segments[start_seg]["start"]
            
            # Fix 1: If this is the start of the song, force start time to 0.0
            # This handles long intros correctly (preventing line 0 from starting at 20s)
            if k == 0 and start_lyric == 0:
                s_time = 0.0

            # Fix 2: Use START of the end_seg as the boundary
            # The anchor line (end_lyric) should START at its matching segment's start.
            # Previously we used ["end"], which pushed the anchor line to after the segment finished!
            e_time = whisper_segments[end_seg]["start"]
            
            # Handle boundary case where start_seg == end_seg (or timing creates 0 duration)
            if e_time < s_time:
                e_time = s_time
            
            block_duration = e_time - s_time
            time_per_lyric = block_duration / lyrics_count if lyrics_count > 0 else 0
            
            for i in range(lyrics_count):
                curr_lyric_idx = start_lyric + i
                
                # Interpolate time
                estimated_start = s_time + (i * time_per_lyric)
                estimated_end = s_time + ((i + 1) * time_per_lyric)
                
                entry = script_entries[curr_lyric_idx]
                lines = []
                if entry.get("japanese"): lines.append(entry["japanese"])
                if entry.get("romaji"): lines.append(entry["romaji"])
                if entry.get("english"): lines.append(entry["english"])
                
                aligned.append({
                    "id": curr_lyric_idx,
                    "start": float(estimated_start),
                    "end": float(estimated_end),
                    "text": "\n".join(lines),
                    "words": []
                })
        
        # Add the final lyric (the loop above goes up to end_lyric - 1)
        last_anchor_lyric, last_anchor_seg = anchors[-1]
        if aligned and aligned[-1]["id"] != last_anchor_lyric:
             # Just append the last one with duration of the last segment
            ws = whisper_segments[last_anchor_seg]
            entry = script_entries[last_anchor_lyric]
            lines = []
            if entry.get("japanese"): lines.append(entry["japanese"])
            if entry.get("romaji"): lines.append(entry["romaji"])
            if entry.get("english"): lines.append(entry["english"])
            
            aligned.append({
                "id": last_anchor_lyric,
                "start": float(ws["start"]), # Should match previous end
                "end": float(ws["end"]),
                "text": "\n".join(lines),
                "words": []
            })

        # Final Sort and Smoothen
        aligned.sort(key=lambda x: x["id"])
        
        # Ensure contiguous timing (no gaps/overlaps) unless gap is large
        for i in range(len(aligned) - 1):
             aligned[i]["end"] = aligned[i+1]["start"]

        log(f"Done! Mapped {num_lines} lyrics using anchor-based alignment")
        return aligned, duration, whisper_segments
    
    # Fallback if Whisper failed
    log("Whisper found too few segments, using even distribution...")
    vocal_start, vocal_end, duration = find_vocal_range_fast(audio_path)
    
    vocal_duration = vocal_end - vocal_start
    time_per_line = vocal_duration / num_lines
    
    aligned = []
    for i, entry in enumerate(script_entries):
        start = vocal_start + (i * time_per_line)
        end = vocal_start + ((i + 1) * time_per_line)
        
        lines = []
        if entry.get("japanese"):
            lines.append(entry["japanese"])
        if entry.get("romaji"):
            lines.append(entry["romaji"])
        if entry.get("english"):
            lines.append(entry["english"])
        
        aligned.append({
            "id": i,
            "start": float(start),
            "end": float(end),
            "text": "\n".join(lines),
            "words": []
        })
    
    log(f"Done! Generated {len(aligned)} subtitles")
    return aligned, duration, []



class VideoRequest(BaseModel):
    url: str
    task: str = "transcribe"
    script: Optional[str] = None
    download_video: bool = False
    skip_ai: bool = False
    separate_vocals: bool = False


class VideoDownloadRequest(BaseModel):
    url: str
    download_subs: bool = False



@app.post("/process-url")
async def process_url(request: VideoRequest):
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"Downloading from {request.url}...")
            info, media_path = await asyncio.to_thread(
                download_youtube, 
                request.url, 
                temp_dir,
                request.download_video
            )
            
            # If we downloaded video, extract audio for processing
            if request.download_video:
                audio_path = os.path.join(temp_dir, "extracted_audio.mp3")
                await asyncio.to_thread(extract_audio_from_video, media_path, audio_path)
            else:
                audio_path = media_path
            
            # Generate a unique name for files that might be saved to static
            unique_name = str(uuid.uuid4())
            media_url = "" # Initialize media_url

            # If video was downloaded, we might want to serve it
            if request.download_video:
                # Move the downloaded video to a static directory if it's to be served
                static_video_name = f"{unique_name}.mp4" # Assuming mp4 for now
                static_video_path = os.path.join(STATIC_DIR, static_video_name)
                shutil.copy(media_path, static_video_path)
                
                # Log the served video info
                served_size_mb = os.path.getsize(static_video_path) / (1024 * 1024)
                print(f"[VIDEO SERVE] Copied to: {static_video_name}")
                print(f"[VIDEO SERVE] Served size: {served_size_mb:.2f} MB")
                print(f"[VIDEO SERVE] URL: http://localhost:8000/static/{static_video_name}")
                
                media_url = f"http://localhost:8000/static/{static_video_name}"

            # Determine the path for processing audio
            processing_audio_path = audio_path # Default to audio_path

            if not os.path.exists(audio_path):
                raise HTTPException(status_code=500, detail="Audio download/extraction failed")
            
            # If skip_ai is requested, just return the media_url and basic info
            if request.skip_ai:
                return {
                    "title": info.get('title', 'Unknown Title'),
                    "thumbnail": info.get('thumbnail', ''),
                    "duration": info.get('duration', 0),
                    "media_url": media_url,
                    "media_type": "video" if request.download_video else "audio",
                    "status": "media_updated"
                }

            # Prepare vocals if requested
            vocals_url = ""
            raw_segments = []
            
            # Should we separate vocals? (requested or needed for script alignment)
            need_vocals = request.separate_vocals or (request.script and request.script.strip())
            
            if need_vocals:
                # Define path for persistent vocals in static directory
                vocals_name = f"{unique_name}_vocals.wav"
                vocals_static_path = os.path.join(STATIC_DIR, vocals_name)
                
                # Extract vocals using demucs
                try:
                    # Create a temp directory inside temp_dir for demucs output
                    demucs_out_dir = os.path.join(temp_dir, "demucs")
                    os.makedirs(demucs_out_dir, exist_ok=True)
                    
                    actual_vocals_path = await asyncio.to_thread(
                        separate_vocals_demucs, 
                        audio_path, 
                        demucs_out_dir
                    )
                    
                    # Copy to static for frontend access
                    shutil.copy(actual_vocals_path, vocals_static_path)
                    vocals_url = f"http://localhost:8000/static/{vocals_name}"
                    
                    # Update processing path to use vocals for better accuracy
                    processing_audio_path = actual_vocals_path
                except Exception as de:
                    print(f"Vocal separation failed: {de}")
                    # Fallback to original audio if separation fails

            # Process based on whether user provided script
            if request.script and request.script.strip():
                segments, duration, raw_segments = await asyncio.to_thread(
                    process_with_script, 
                    processing_audio_path, 
                    request.script,
                    None # Already separated above if needed
                )
            else:
                segments, whisper_info = await asyncio.to_thread(
                    run_whisper_transcription, 
                    processing_audio_path, 
                    request.task
                )
                raw_segments = segments
                duration = whisper_info.duration if hasattr(whisper_info, 'duration') else info.get('duration', 0)
            
            return {
                "title": info.get('title', 'Unknown Title'),
                "thumbnail": info.get('thumbnail', ''),
                "duration": info.get('duration', duration),
                "segments": segments,
                "raw_segments": raw_segments,
                "media_url": media_url,
                "vocals_url": vocals_url,
                "media_type": "video" if request.download_video else "audio"
            }
            
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process-file")
async def process_file(
    file: UploadFile = File(...),
    task: str = Form("transcribe"),
    script: Optional[str] = Form(None),
    separate_vocals: bool = Form(False)
):
    try:
        # Create uploads directory in static
        UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")
        os.makedirs(UPLOADS_DIR, exist_ok=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. Save uploaded file to STATIC uploads (persistent for session/project reload)
            ext = os.path.splitext(file.filename)[1]
            if not ext: ext = ".tmp"
            
            unique_name = f"{uuid.uuid4()}{ext}"
            saved_path = os.path.join(UPLOADS_DIR, unique_name)
            
            # Write directly to static
            with open(saved_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            print(f"Saved uploaded file to: {saved_path}")
            
            # Generate public URL
            media_url = f"http://localhost:8000/static/uploads/{unique_name}"
            
            # 2. Extract audio for processing (using temp dir)
            # Check if it's a video file
            video_extensions = ['.mp4', '.mkv', '.webm', '.avi', '.mov']
            is_video = any(file.filename.lower().endswith(e) for e in video_extensions)
            
            if is_video:
                audio_path = os.path.join(temp_dir, "extracted_audio.mp3")
                await asyncio.to_thread(extract_audio_from_video, saved_path, audio_path)
            else:
                audio_path = saved_path
            
            # Determine the path for processing audio
            processing_audio_path = audio_path
            vocals_url = ""

            # Should we separate vocals?
            need_vocals = separate_vocals or (script and script.strip())
            
            if need_vocals:
                # Define path for persistent vocals
                vocals_name = f"{os.path.splitext(unique_name)[0]}_vocals.wav"
                vocals_static_path = os.path.join(STATIC_DIR, vocals_name)
                
                try:
                    demucs_out_dir = os.path.join(temp_dir, "demucs")
                    os.makedirs(demucs_out_dir, exist_ok=True)
                    
                    actual_vocals_path = await asyncio.to_thread(
                        separate_vocals_demucs, 
                        audio_path, 
                        demucs_out_dir
                    )
                    shutil.copy(actual_vocals_path, vocals_static_path)
                    vocals_url = f"http://localhost:8000/static/{vocals_name}"
                    processing_audio_path = actual_vocals_path
                except Exception as de:
                    print(f"Vocal separation failed: {de}")

            # Process based on whether user provided script
            if script and script.strip():
                segments, duration, raw_segments = await asyncio.to_thread(
                    process_with_script,
                    processing_audio_path,
                    script,
                    None
                )
            else:
                segments, whisper_info = await asyncio.to_thread(
                    run_whisper_transcription,
                    processing_audio_path,
                    task
                )
                raw_segments = segments
                duration = whisper_info.duration if hasattr(whisper_info, 'duration') else 0
            
            return {
                "title": file.filename,
                "thumbnail": "",
                "duration": duration,
                "segments": segments,
                "raw_segments": raw_segments,
                "media_url": media_url,
                "vocals_url": vocals_url,
                "media_type": "video" if is_video else "audio"
            }

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/get-video-formats")
async def get_formats_endpoint(request: VideoDownloadRequest):
    try:
        ydl_opts = get_common_ydl_opts()
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # We use extract_info with download=False to get metadata
            info = await asyncio.to_thread(ydl.extract_info, request.url, download=False)
            
            return {
                "title": info.get('title'),
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
            }
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))


@app.post("/download-video-tool")
async def download_video_tool(request: VideoDownloadRequest):
    try:
        # Create a unique directory in static for this download
        # This allows us to serve the file back to the user
        request_id = str(uuid.uuid4())
        # We use a 'temp_downloads' folder inside static
        SAVE_DIR = os.path.join(STATIC_DIR, "temp_downloads", request_id)
        os.makedirs(SAVE_DIR, exist_ok=True)
        
        # Use clean config for best quality
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(SAVE_DIR, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
        }
            
        if request.download_subs:
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = ['en', 'ja'] 
            
        print(f"Downloading to temp storage: {SAVE_DIR}...")
        
        filename = ""
        file_url = ""
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download
            info = await asyncio.to_thread(ydl.extract_info, request.url, download=True)
            
            # Log quality info (same as before)
            if 'requested_formats' in info:
                video_fmt = info['requested_formats'][0] if len(info['requested_formats']) > 0 else {}
                format_note = video_fmt.get('format_note', info.get('format', 'unknown'))
            else:
                format_note = info.get('format', 'unknown')

            print(f"[DISK DOWNLOAD] Quality: {format_note}")
            
            # Find the downloaded file
            # We look for the video file in the directory
            files = os.listdir(SAVE_DIR)
            video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.webm'))]
            
            if video_files:
                filename = video_files[0]
                # Construct URL
                # NOTE: This assumes the app is running on port 8000
                file_url = f"http://localhost:8000/static/temp_downloads/{request_id}/{filename}"
            
        if file_url:
            return {
                "status": "ready", 
                "url": file_url, 
                "filename": filename,
                "message": "Download ready"
            }
        else:
             raise HTTPException(status_code=500, detail="File processing failed")

    except Exception as e:
        print(f"Download specific failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
