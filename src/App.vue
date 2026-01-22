<script setup>
import { ref, computed, watch } from 'vue';

// Input state
const inputType = ref('url'); // 'url' or 'upload'
const url = ref('');
const fileObj = ref(null);
const task = ref('transcribe'); // 'transcribe' or 'translate'

// Script mode
const useCustomScript = ref(false);
const userScript = ref('');
const scriptFile = ref(null);


// Processing state
const loading = ref(false);
const result = ref(null);
const error = ref('');

const drawer = ref(true); // Sidebar toggle

// Download Tool State
const videoInfo = ref(null);

const downloadSubs = ref(false);
const isDownloading = ref(false);
const downloadStatus = ref('');
const loadingFormats = ref(false);

// Save Dialog State
const showSaveDialog = ref(false);
const saveWithVideo = ref(false);


// Vocals Player Settings
const showVocalsPlayer = ref(false); // Toggle in settings
const vocalsExpanded = ref(false); // Collapsible state


// Playback Control
let stopAtTime = -1;
let isSegmentPlay = false;

const fetchVideoInfo = async () => {
    const targetUrl = result.value?.source_url || url.value;
    if (!targetUrl) return;
    loadingFormats.value = true;
    error.value = '';
    try {
        const res = await fetch('http://localhost:8000/get-video-formats', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ url: targetUrl })
        });
        if(!res.ok) throw new Error("Failed to fetch info");
        videoInfo.value = await res.json();
    } catch (e) {
        error.value = "Could not fetch video info: " + e.message;
    } finally {
        loadingFormats.value = false;
    }
};

const performDownload = async () => {
    const targetUrl = result.value?.source_url || url.value;
    if (!targetUrl) return;
    isDownloading.value = true;
    downloadStatus.value = 'Preparing download...';
    try {
        const res = await fetch('http://localhost:8000/download-video-tool', {
             method: 'POST',
             headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({
                 url: targetUrl,
                 download_subs: downloadSubs.value
             })
        });
        const data = await res.json();
        if(!res.ok) throw new Error(data.detail || "Download failed");
        
        // Trigger browser download
        if (data.url) {
            const link = document.createElement('a');
            link.href = data.url;
            link.download = data.filename || 'video.mp4';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            triggerUndo(`Download started: ${data.filename}`);
        } else {
             triggerUndo("Download completed (server side)");
        }

        downloadStatus.value = 'Done!';
        setTimeout(() => downloadStatus.value = '', 3000);
    } catch (e) {
        error.value = e.message;
        downloadStatus.value = 'Failed';
    } finally {
        isDownloading.value = false;
    }
};

watch(url, () => {
    videoInfo.value = null;
    downloadStatus.value = '';
});


// ...

// Undo System
const undoStack = ref([]);
const showUndo = ref(false);
const undoMessage = ref('');
const undoTimeout = ref(null);

const commitAction = (segment, field, oldValue, message) => {
    undoStack.value.push({
        type: 'field',
        segment,
        field,
        value: oldValue,
        message
    });
    triggerUndo(message);
};

const commitComplexAction = (restoreFn, message) => {
    undoStack.value.push({
        type: 'callback',
        restore: restoreFn,
        message
    });
    triggerUndo(message);
};

const triggerUndo = (message) => {
    undoMessage.value = message;
    showUndo.value = true;
    if (undoTimeout.value) clearTimeout(undoTimeout.value);
    undoTimeout.value = setTimeout(() => showUndo.value = false, 5000);
};

const performUndo = () => {
    if (undoStack.value.length === 0) return;
    const action = undoStack.value.pop();
    
    if (action.type === 'field') {
        action.segment[action.field] = action.value;
    } else if (action.type === 'callback') {
        action.restore();
    }
    
    showUndo.value = false;
};

const deleteSegment = (index) => {
    const list = result.value.segments;
    const deleted = list[index];
    
    commitComplexAction(() => {
        list.splice(index, 0, deleted);
    }, 'Restored deleted segment');
    
    list.splice(index, 1);
};



const addSegment = (index) => {
    const list = result.value.segments;
    const current = index >= 0 ? list[index] : list[list.length - 1];
    
    // Default new segment
    const newStart = current ? current.end : 0;
    const newEnd = current ? current.end + 2 : 2;
    
    const newSegment = {
        id: Date.now(),
        start: newStart,
        end: newEnd,
        text: '',
        status: 'pending'
    };
    
    commitComplexAction(() => {
        const idx = list.findIndex(s => s.id === newSegment.id);
        if (idx !== -1) list.splice(idx, 1);
    }, 'Undid add segment');
    
    if (index === -1) {
         // Insert at end (if button clicked at bottom)
         // But usually Add Below means index + 1
         list.push(newSegment);
    } else {
        list.splice(index + 1, 0, newSegment);
    }
};



const snapToPrevious = (index) => {
    if (index <= 0) return;
    const current = result.value.segments[index];
    const prev = result.value.segments[index - 1];
    
    commitAction(current, 'start', current.start, 'Snapped start to previous end');
    current.start = prev.end;
};

const projectFileInput = ref(null);

const saveProject = () => {
    if (!result.value) return;
    // Show save dialog
    showSaveDialog.value = true;
};

const performSave = async () => {
    if (!result.value) return;
    
    // Gather video metadata
    let videoMetadata = null;
    if (mediaPlayer.value) {
        videoMetadata = {
            duration: mediaPlayer.value.duration,
            currentTime: mediaPlayer.value.currentTime,
            videoWidth: mediaPlayer.value.videoWidth,
            videoHeight: mediaPlayer.value.videoHeight,
        };
    }
    
    const projectData = {
        version: 2, // Increment version for new format
        timestamp: new Date().toISOString(),
        source: {
            type: inputType.value,
            url: url.value,
            filename: fileObj.value?.name,
            media_url: mediaUrl.value, // Persist the served/external URL
            media_type: mediaType.value,
        },
        video: videoMetadata,
        result: result.value
    };
    
    const blob = new Blob([JSON.stringify(projectData, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    const filename = `${(result.value.title || 'autosubs_project').replace(/[^a-z0-9]/gi, '_')}.json`;
    link.download = filename;
    link.click();
    
    // Close dialog
    showSaveDialog.value = false;
    
    // If user wants to download video as well (only for URL-based projects)
    if (saveWithVideo.value && inputType.value === 'url' && url.value) {
        triggerUndo('Project saved! Downloading video...');
        
        // Trigger video download
        try {
            const res = await fetch('http://localhost:8000/download-video-tool', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    url: url.value,
                    download_subs: false // Don't include subs, we have our own
                })
            });
            const data = await res.json();
            if(!res.ok) throw new Error(data.detail || "Download failed");
            
            triggerUndo('Video downloaded successfully to downloads folder!');
        } catch (e) {
            error.value = 'Project saved, but video download failed: ' + e.message;
        }
    } else {
        // Show helpful message
        triggerUndo(`Project saved! ${inputType.value === 'upload' ? 'Keep the video file in the same folder for easy reloading.' : 'Video URL saved - can reload anytime.'}`);
    }
};

const triggerLoadProject = () => {
    projectFileInput.value.click();
};

const onProjectFileSelect = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        try {
            const data = JSON.parse(e.target.result);
            if (data.result && data.result.segments) {
                undoStack.value = [];
                result.value = data.result;
                
                if (data.source) {
                    inputType.value = data.source.type || 'url';
                    mediaType.value = data.source.media_type || 'video';
                    
                    if (data.source.type === 'url') {
                        url.value = data.source.url;
                        // If it's a URL, we can attempt to fetch info for the download tool
                        if(url.value) fetchVideoInfo();
                        
                        // For URL-based projects, try to restore the media URL
                        if (data.source.media_url) {
                            mediaUrl.value = data.source.media_url;
                        }
                    } else if (data.source.type === 'upload') {
                        // For uploaded files, prompt user to select the video file
                        const videoFileName = data.source.filename || 'video file';
                        triggerUndo(`Project loaded! Please select the video file (${videoFileName}) to continue editing.`);
                        
                        // Create a file input to let user select the video
                        const videoInput = document.createElement('input');
                        videoInput.type = 'file';
                        videoInput.accept = 'video/*,audio/*';
                        videoInput.onchange = (e) => {
                            const videoFile = e.target.files[0];
                            if (videoFile) {
                                fileObj.value = videoFile;
                                // The watcher will create the object URL automatically
                                triggerUndo('Video file loaded successfully!');
                            }
                        };
                        // Auto-trigger after a short delay
                        setTimeout(() => videoInput.click(), 500);
                    }
                }
                
                drawer.value = false; 
            } else {
                throw new Error("Invalid project format");
            }
        } catch (err) {
            error.value = "Failed to load project: " + err.message;
        }
    };
    reader.readAsText(file);
    event.target.value = '';
};

const adjustTime = (segment, type, amount) => {
    commitAction(segment, type, segment[type], `Adjusted ${type} time`);
    const val = segment[type] + amount;
    segment[type] = Math.max(0, Math.round(val * 1000) / 1000);
};

const setCurrentTime = (segment, type) => {
    if (!mediaPlayer.value) return;
    commitAction(segment, type, segment[type], `Set ${type} to playhead`);
    segment[type] = Math.round(mediaPlayer.value.currentTime * 1000) / 1000;
};

// Computed stats
const totalSegments = computed(() => result.value?.segments?.length || 0);
const totalDuration = computed(() => result.value?.duration ? formatTime(result.value.duration) : '00:00:00');



const formatTime = (seconds) => {
  if (!seconds && seconds !== 0) return '00:00:00,000';
  const date = new Date(0);
  date.setMilliseconds(seconds * 1000);
  return date.toISOString().substr(11, 12).replace('.', ',');
};

const parseTime = (timeStr) => {
  if (!timeStr) return 0;
  try {
    const parts = timeStr.replace(',', '.').split(':');
    let seconds = 0;
    if (parts.length === 3) {
      seconds += parseInt(parts[0]) * 3600;
      seconds += parseInt(parts[1]) * 60;
      seconds += parseFloat(parts[2]);
    } else if (parts.length === 2) {
      seconds += parseInt(parts[0]) * 60;
      seconds += parseFloat(parts[1]);
    } else {
      seconds = parseFloat(timeStr);
    }
    return isNaN(seconds) ? 0 : seconds;
  } catch (e) {
    return 0;
  }
};



const onScriptFileSelect = (files) => {
  // Handle both Vuetify file input event (array) and native input (FileList)
  let file = null;
  
  if (files instanceof FileList) {
      file = files[0];
  } else if (Array.isArray(files)) {
      file = files[0];
  } else {
      file = files;
  }

  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    userScript.value = e.target.result;
  };
  reader.readAsText(file);
};

const exportSRT = () => {
  if (!result.value) return;
  let srtContent = '';
  result.value.segments.forEach((seg, index) => {
    srtContent += `${index + 1}\n`;
    srtContent += `${formatTime(seg.start)} --> ${formatTime(seg.end)}\n`;
    srtContent += `${seg.text}\n\n`;
  });

  const blob = new Blob([srtContent], { type: 'text/plain;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  const filename = (result.value.title || 'subtitles').replace(/[<>:"/\\|?*]/g, '_');
  link.download = `${filename}.srt`;
  link.click();
};

const clearResults = () => {
  result.value = null;
  error.value = '';
};

// Watch for file selection to auto-enable custom script if .txt/.srt file
watch(scriptFile, (newFile) => {
  if (newFile) {
    onScriptFileSelect(newFile);
  }
});
// Audio/Video Playback State
const mediaUrl = ref('');
const vocalsUrl = ref(''); // New state for vocals
const mediaType = ref('audio'); // 'audio' or 'video'
const mediaPlayer = ref(null);
const isUpdatingPlayer = ref(false);
const isPlaying = ref(false);

const updatePlayerQuality = async () => {
    const targetUrl = result.value?.source_url || url.value;
    if (!targetUrl) return;
    
    isUpdatingPlayer.value = true;
    try {
        const res = await fetch('http://localhost:8000/process-url', {
             method: 'POST',
             headers: {'Content-Type': 'application/json'},
             body: JSON.stringify({
                 url: targetUrl,
                 download_video: true,
                 skip_ai: true
             })
        });
        const data = await res.json();
        if(!res.ok) throw new Error(data.detail || "Update failed");
        
        if (data.media_url) {
            mediaUrl.value = data.media_url;
            mediaType.value = data.media_type || 'video';
            triggerUndo(`Player quality updated`);
        }
    } catch (e) {
        error.value = "Failed to update player quality: " + e.message;
    } finally {
        isUpdatingPlayer.value = false;
    }
};

const currentPlayingIndex = ref(-1);

// Watch for file selection to create object URL for playback
watch(fileObj, (newFile) => {
  if (inputType.value === 'upload' && newFile) {
    if (mediaUrl.value && mediaUrl.value.startsWith('blob:')) {
         URL.revokeObjectURL(mediaUrl.value);
    }
    mediaUrl.value = URL.createObjectURL(newFile);
    
    // Detect type
    const ext = newFile.name.split('.').pop().toLowerCase();
    if (['mp4', 'webm', 'ogg', 'mov', 'mkv'].includes(ext)) {
        mediaType.value = 'video';
    } else {
        mediaType.value = 'audio';
    }
  } else if (inputType.value === 'upload' && !newFile) {
    mediaUrl.value = '';
  }
});

const checkTime = () => {
    if (!mediaPlayer.value) return;
    const player = mediaPlayer.value;
    
    // Check if we reached the stop time
    if (stopAtTime > 0 && player.currentTime >= stopAtTime) {
        player.pause();
        stopAtTime = -1; // Reset
        isPlaying.value = false;
    }
};

const playSegment = (index) => {
  if (!mediaPlayer.value || !result.value) return;
  
  const segment = result.value.segments[index];
  const player = mediaPlayer.value;
  
  // Set playing index immediately for visual feedback
  currentPlayingIndex.value = index;
  
  // Flag that this is a segment play so manual handler doesn't clear it
  isSegmentPlay = true;
  
  // If clicking same segment while playing, restart from beginning
  if (isPlaying.value && player.currentTime >= segment.start && player.currentTime <= segment.end) {
    player.currentTime = segment.start;
    stopAtTime = segment.end;
    return;
  }
  
  // Play segment
  player.currentTime = segment.start;
  stopAtTime = segment.end;
  
  player.play().then(() => {
    isPlaying.value = true;
  }).catch(e => console.error("Playback failed", e));
};



const toggleGlobalPlay = () => {
    if (!mediaPlayer.value) return;
    if (isPlaying.value) {
        mediaPlayer.value.pause();
    } else {
        // When manually playing globally, clear segment constraints
        stopAtTime = -1;
        currentPlayingIndex.value = -1;
        mediaPlayer.value.play();
    }
};

const handleManualPlay = () => {
    isPlaying.value = true;
    
    if (isSegmentPlay) {
        isSegmentPlay = false;
        return;
    }

    // When the user manually interacts with the master player,
    // we should usually disable the "stop at segment end" behavior
    // so they can freely navigate the video.
    stopAtTime = -1;
    currentPlayingIndex.value = -1;
};

const handleManualPause = () => {
    isPlaying.value = false;
};

const toggleSegmentStatus = (segment) => {
    segment.status = segment.status === 'good' ? 'pending' : 'good';
};

const parseScriptText = (script) => {
    // Split by empty lines to get blocks
    return script.split(/\n\s*\n/)
        .map(block => block.trim())
        .filter(block => block.length > 0);
};

const updateTextOnly = () => {
    if (!result.value || !userScript.value) return;
    
    const newTexts = parseScriptText(userScript.value);
    const validSegments = result.value.segments;
    
    if (newTexts.length === 0) {
        error.value = "Script appears empty.";
        return;
    }

    // Save state for undo
    const oldTexts = validSegments.map(s => s.text);
    
    commitComplexAction(() => {
        validSegments.forEach((s, i) => {
            if (oldTexts[i] !== undefined) s.text = oldTexts[i];
        });
    }, 'Undid text update');
    
    // Apply new text
    let updateCount = 0;
    validSegments.forEach((segment, i) => {
        if (i < newTexts.length) {
            segment.text = newTexts[i];
            updateCount++;
        }
    });
    
    // Notify user
    triggerUndo(`Updated text for ${updateCount} segments`);
    
    // Warning if length mismatch
    if (Math.abs(validSegments.length - newTexts.length) > 0) {
        error.value = `Note: Segment count mismatch. Timeline has ${validSegments.length}, Script has ${newTexts.length}.`;
        // Auto-clear warning after 5s
        setTimeout(() => error.value = '', 5000);
    }
};

const processVideo = async () => {
    loading.value = true;
    error.value = '';
    
    // If we are just updating text, hijack this function or ensure the button calls updateTextOnly directly.
    // ... rest of existing processVideo ...
    result.value = null; // This clears result, so updateTextOnly must NOT use this function.
    vocalsUrl.value = ''; // Reset

  try {
    let apiEndpoint = '';
    let body = null;
    let headers = {};

    const scriptContent = useCustomScript.value ? userScript.value : null;
    const activeTask = useCustomScript.value ? 'transcribe' : task.value;

    if (inputType.value === 'url') {
      if (!url.value) throw new Error("Please enter a URL");
      apiEndpoint = 'http://localhost:8000/process-url';
      headers = { 'Content-Type': 'application/json' };
      body = JSON.stringify({ 
        url: url.value, 
        task: activeTask, 
        script: scriptContent,
        download_video: true,
        separate_vocals: showVocalsPlayer.value
      });
    } else {
      if (!fileObj.value) throw new Error("Please select a file");
      apiEndpoint = 'http://localhost:8000/process-file';
      const formData = new FormData();
      formData.append('file', fileObj.value);
      formData.append('task', activeTask);
      if (scriptContent) formData.append('script', scriptContent);
      formData.append('separate_vocals', showVocalsPlayer.value);
      body = formData;
    }

    const response = await fetch(apiEndpoint, {
      method: 'POST',
      headers: inputType.value === 'url' ? headers : {},
      body: body
    });

    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to process');
    }

    const data = await response.json();
    
    // Store source info in result for UI consistency
    data.source_type = inputType.value;
    data.source_url = inputType.value === 'url' ? url.value : null;

    // Initialize status for each segment
    if (data.segments) {
        data.segments = data.segments.map(s => ({ ...s, status: 'pending' }));
    }
    
    result.value = data;
    
    // Handle Media URL
    if (inputType.value === 'url' && data.media_url) {
        mediaUrl.value = data.media_url;
        mediaType.value = data.media_type || 'video';
    } else if (inputType.value === 'upload') {
        // mediaUrl is already set by the watcher
         const ext = fileObj.value.name.split('.').pop().toLowerCase();
        if (['mp4', 'webm', 'ogg', 'mov', 'mkv'].includes(ext)) {
            mediaType.value = 'video';
        } else {
            mediaType.value = 'audio';
        }
    }

    // Handle Vocals URL
    if (data.vocals_url) {
        vocalsUrl.value = data.vocals_url;
    }
    
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
};

// Clean up
watch(result, (val) => {
    if(!val) {
        if(mediaUrl.value && inputType.value === 'url') {
             mediaUrl.value = '';
        }
        vocalsUrl.value = ''; // Clear vocals
        if(mediaPlayer.value) {
             mediaPlayer.value.pause();
             isPlaying.value = false;
        }
    }
});

// Collapse sidebar when result is loaded to focus on editor
watch(result, (val) => {
    if (val) {
        drawer.value = false;
    }
});

// Auto-scroll to active segment (only within timeline container)
watch(currentPlayingIndex, (newIndex) => {
    if (newIndex !== -1) {
        // Use setTimeout to allow DOM update class application
        setTimeout(() => {
            const element = document.getElementById(`segment-${newIndex}`);
            const container = document.querySelector('.timeline-container');
            
            if (element && container) {
                // Calculate position to scroll to (center the element in the container)
                const elementTop = element.offsetTop;
                const elementHeight = element.offsetHeight;
                const containerHeight = container.clientHeight;
                
                // Scroll position to center the element
                const scrollTo = elementTop - (containerHeight / 2) + (elementHeight / 2);
                
                // Scroll only the timeline container, not the whole page
                container.scrollTo({
                    top: scrollTo,
                    behavior: 'smooth'
                });
            }
        }, 100);
    }
});
</script>

<template>
  <v-app class="app-bg">
    <!-- Modern Sidebar Navigation -->
    <v-navigation-drawer
      v-model="drawer"
      width="400"
      app 
      elevation="0"
      class="modern-sidebar"
      floating
    >
      <!-- 1. Header Section -->
      <div class="sidebar-header pb-4 pt-8 px-6">
        <div class="d-flex align-center mb-6">
            <div class="logo-box mr-3">
                 <img src="/logo.svg?v=2" alt="AutoSubs Logo" class="app-logo" height="40" width="40" style="display: block;" />
            </div>
            <h2 class="text-h5 font-weight-black text-slate-800 tracking-tight mb-0" style="line-height: 1; padding-top: 2px;">AutoSubs</h2>
        </div>

        <!-- Source Toggle (Segmented Control) -->
        <div class="source-toggle-wrapper p-1 bg-slate-100 rounded-xl">
            <v-btn-toggle
              v-model="inputType"
              mandatory
              class="w-100 no-border"
              color="primary"
              rounded="xl"
              variant="flat"
              density="comfortable"
              divided="false"
            >
              <v-btn value="url" class="flex-grow-1 toggle-pill" :ripple="false">
                <v-icon start size="18">mdi-youtube</v-icon>
                YouTube
              </v-btn>
              <v-btn value="upload" class="flex-grow-1 toggle-pill" :ripple="false">
                <v-icon start size="18">mdi-file-video</v-icon>
                Upload
              </v-btn>
            </v-btn-toggle>
        </div>
      </div>

      <!-- 2. Scrollable Content -->
      <div class="sidebar-content px-6 pb-24">
        
        <!-- Input Area -->
        <div class="input-card mb-6">
            <v-expand-transition>
                <div v-if="inputType === 'url'">
                    <v-text-field
                      v-model="url"
                      placeholder="Paste YouTube URL"
                      variant="outlined"
                      color="primary"
                      bg-color="white"
                      prepend-inner-icon="mdi-link"
                      hide-details="auto"
                      class="modern-input"
                      density="comfortable"
                      rounded="lg"
                    ></v-text-field>
                </div>
                <div v-else>
                     <v-file-input
                      v-model="fileObj"
                      label="Choose File"
                      variant="outlined"
                      color="primary"
                      bg-color="white"
                      prepend-icon=""
                      prepend-inner-icon="mdi-paperclip"
                      accept="video/*,audio/*"
                      hide-details="auto"
                      class="modern-input"
                      show-size
                      density="comfortable"
                      rounded="lg"
                    ></v-file-input>
                </div>
            </v-expand-transition>
        </div>

        <div class="section-divider mb-6">
            <span class="divider-label">CONFIGURATION</span>
        </div>

        <!-- Workflow Mode Card -->
        <div class="workflow-card bg-white rounded-xl border-slate-200 pa-4 mb-6 relative">
            
            <!-- Custom Script Toggle Row -->
            <div class="d-flex align-center justify-space-between mb-4">
                <div class="d-flex align-center">
                    <div class="icon-box-small icon-box-primary mr-3">
                        <v-icon size="20">mdi-script-text</v-icon>
                    </div>
                    <div>
                        <div class="text-subtitle-2 font-weight-bold text-slate-700">Custom Script</div>
                        <div class="text-caption text-slate-400">Align existing lyrics</div>
                    </div>
                </div>
                <v-switch
                    v-model="useCustomScript"
                    color="primary"
                    hide-details
                    inset
                    density="compact"
                    class="modern-switch"
                ></v-switch>
            </div>

            <v-expand-transition>
                <!-- AI Tasks -->
                <div v-if="!useCustomScript">
                     <v-radio-group v-model="task" hide-details class="modern-radio-group">
                        <v-radio value="transcribe" color="primary" class="mb-3 radio-item">
                            <template v-slot:label>
                                <div class="ml-2">
                                    <div class="font-weight-bold text-slate-700">🇯🇵 Transcribe Japanese</div>
                                    <div class="text-caption text-slate-400">Generate JP + Romaji</div>
                                </div>
                            </template>
                        </v-radio>
                        <v-radio value="translate" color="secondary" class="radio-item">
                            <template v-slot:label>
                                <div class="ml-2">
                                    <div class="font-weight-bold text-slate-700">🇬🇧 Translate to English</div>
                                    <div class="text-caption text-slate-400">Direct English subs</div>
                                </div>
                            </template>
                        </v-radio>
                     </v-radio-group>
                </div>

                <!-- Script Editor -->
                <div v-else class="script-editor-wrapper">
                    <!-- Tools -->
                    <div class="d-flex align-center justify-space-between mb-2">
                         <v-btn 
                            prepend-icon="mdi-upload"
                            variant="text"
                            size="small"
                            color="primary"
                            class="px-0"
                            @click="$refs.scriptFileInput.click()"
                        >
                            Load File
                        </v-btn>
                        <!-- Hidden Input -->
                        <input 
                            type="file" 
                            ref="scriptFileInput" 
                            style="display: none" 
                            accept=".txt,.srt,.vtt,.json" 
                            @change="(e) => onScriptFileSelect(e.target.files)"
                        />

                        <v-btn size="x-small" variant="text" prepend-icon="mdi-help-circle-outline" color="slate-400">
                             Format
                             <v-menu
                                activator="parent"
                                open-on-hover
                                location="top"
                                max-width="300"
                                offset="10"
                            >
                                <v-sheet class="pa-3 rounded-lg" color="#0f172a" theme="dark">
                                   <div class="text-caption font-weight-bold mb-1 text-white">Script Format:</div>
                                   <div class="text-caption text-grey-lighten-2" style="font-family: monospace; line-height: 1.4;">
                                       Japanese Line<br>
                                       Romaji Line<br>
                                       (Translation)<br>
                                       <br>
                                       [Empty line between blocks]
                                   </div>
                </v-sheet>
                            </v-menu>
                        </v-btn>
                    </div>
                    
                    <div class="editor-box">
                        <textarea 
                            v-model="userScript" 
                            class="styled-textarea"
                            placeholder="Paste your lyrics or script here..."
                            rows="8"
                        ></textarea>
                        <div class="editor-footer">
                             {{ userScript ? userScript.split('\n').filter(l=>l.trim()).length : 0 }} lines
                        </div>
                    </div>
                </div>
            </v-expand-transition>
        </div>

        <!-- Advanced Settings -->
        <div class="workflow-card bg-white rounded-xl border-slate-200 pa-4 mb-6 relative">
            <div class="d-flex align-center justify-space-between">
                <div class="d-flex align-center">
                    <div class="icon-box-small icon-box-primary mr-3">
                        <v-icon size="20">mdi-cog</v-icon>
                    </div>
                    <div>
                        <div class="text-subtitle-2 font-weight-bold text-slate-700">Show Separated Vocals</div>
                        <div class="text-caption text-slate-400">Display isolated vocal track (for music)</div>
                    </div>
                </div>
                <v-switch
                    v-model="showVocalsPlayer"
                    color="primary"
                    hide-details
                    inset
                    density="compact"
                    class="modern-switch"
                ></v-switch>
            </div>
        </div>

        <!-- Errors -->
        <v-slide-y-transition>
            <div v-if="error" class="error-card pa-4 rounded-lg bg-red-50 text-red-600 mb-6 border-red-100 d-flex align-start">
                <v-icon color="error" class="mr-3" size="20">mdi-alert-circle</v-icon>
                <div class="text-caption font-weight-bold">{{ error }}</div>
                <v-btn icon="mdi-close" size="x-small" variant="text" color="error" class="ml-auto mt-n1" @click="error = ''"></v-btn>
            </div>
        </v-slide-y-transition>

      </div>

      <!-- 3. Fixed Bottom Action Bar -->
      <div class="sidebar-footer px-6 py-4 bg-white border-t border-slate-100">
            <div v-if="!result">
                <v-btn
                    block
                    color="primary"
                    size="x-large"
                    :loading="loading"
                    @click="processVideo"
                    class="main-action-btn"
                    rounded="xl"
                    elevation="4"
                    height="56"
                >
                    <v-icon class="mr-3">mdi-sparkles</v-icon>
                    {{ useCustomScript ? 'Generate Timing' : 'Start Processing' }}
                </v-btn>
            </div>

            <!-- Update Actions -->
            <div v-else class="d-flex flex-column gap-2">
                <v-btn
                    v-if="useCustomScript"
                    block
                    color="primary"
                    variant="flat"
                    size="large"
                    @click="updateTextOnly"
                    rounded="xl"
                    class="main-action-btn font-weight-bold mb-3"
                    prepend-icon="mdi-text-box-check"
                    elevation="4"
                    height="56"
                >
                    Update Text Only
                </v-btn>

                <v-btn
                    block
                    color="grey-darken-1"
                    variant="text"
                    @click="processVideo"
                    :loading="loading"
                    class="text-caption"
                >
                    <v-icon start size="small">mdi-refresh</v-icon>
                    Regenerate All (Re-run AI)
                </v-btn>
            </div>
      </div>
    </v-navigation-drawer>

    <!-- Main Content Area -->
    <v-main>
      <v-container fluid class="pa-6 full-height-container">
          
        <!-- Header Banner with Toggle -->
        <div class="hero-header mb-8">
            <div class="d-flex align-center w-100 justify-space-between">
                
                <div class="d-flex align-center">
                    <v-btn icon="mdi-menu" variant="text" @click="drawer = !drawer" class="mr-3 text-white"></v-btn>
                    <img src="/logo.svg?v=2" alt="AutoSubs Logo" class="app-logo mr-4" height="48" width="48" />
                    <div>
                        <h1 class="hero-title">AutoSubs</h1>
                        <div class="hero-subtitle" style="max-width: 400px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                            {{ (result && result.title) ? result.title : 'Studio Dashboard' }}
                        </div>
                    </div>
                </div>

                <v-spacer></v-spacer>

                <div class="hero-actions d-flex align-center" v-if="result">
                    <v-btn 
                        color="white" 
                        variant="text" 
                        class="mr-2"
                        prepend-icon="mdi-folder-open" 
                        @click="triggerLoadProject"
                    >
                        Load
                    </v-btn>
                    <v-btn 
                        color="white" 
                        variant="text" 
                         class="mr-2"
                        prepend-icon="mdi-content-save" 
                        @click="saveProject" 
                    >
                        Save
                    </v-btn>
                    <v-divider vertical class="mx-3 bg-white" thickness="2" style="opacity: 0.3; height: 24px; align-self: center;"></v-divider>
                    <v-btn 
                        color="white" 
                        variant="flat" 
                        prepend-icon="mdi-download" 
                        @click="exportSRT" 
                        class="export-btn"
                    >
                        Export .SRT
                    </v-btn>
                </div>
            </div>
        </div>

        <!-- Hidden Project Loader -->
        <input 
            type="file" 
            ref="projectFileInput" 
            style="display: none" 
            accept=".json" 
            @change="onProjectFileSelect"
        />

        <!-- Empty State (Centered) -->
        <div v-if="!result && !loading" class="empty-state-wrapper">
            <div class="empty-state">
                <div class="empty-icon" style="background-color: #fff1f2;">
                    <v-icon size="80" color="primary">mdi-waveform</v-icon>
                </div>
                <h2 class="empty-title">Ready to Generate Subtitles</h2>
                <div class="d-flex justify-center mb-6">
                    <v-btn 
                        variant="outlined" 
                        color="primary" 
                        prepend-icon="mdi-folder-open"
                        class="mr-4"
                        @click="triggerLoadProject"
                    >
                        Load Project
                    </v-btn>
                </div>
                <p class="empty-desc">
                    Configure your options in the sidebar to get started.
                </p>
                
                <div class="feature-chips">
                    <v-chip variant="tonal" color="primary" class="ma-1">
                    <v-icon start size="small">mdi-microphone</v-icon>
                    Auto Transcription
                    </v-chip>
                    <v-chip variant="tonal" color="secondary" class="ma-1">
                    <v-icon start size="small">mdi-timer</v-icon>
                    Smart Timing
                    </v-chip>
                    <v-chip variant="tonal" color="success" class="ma-1">
                    <v-icon start size="small">mdi-translate</v-icon>
                    Japanese → Romaji
                    </v-chip>
                </div>
            </div>
        </div>

        <!-- Loading State -->
        <div v-if="loading" class="empty-state-wrapper">
             <div class="loading-state">
                <div class="loading-animation">
                  <v-progress-circular 
                    indeterminate 
                    color="primary" 
                    size="80" 
                    width="6"
                  ></v-progress-circular>
                </div>
                <h2 class="loading-title">Processing Media...</h2>
                <p class="loading-desc">
                  {{ useCustomScript ? 'Analyzing audio energy and aligning your transcript...' : 'Running AI transcription and timing analysis...' }}
                </p>
                <p class="loading-hint text-caption text-medium-emphasis">This may take 1-3 minutes depending on video length</p>
              </div>
        </div>

        <!-- Results Area (Full Width) -->
        <div v-if="result" class="results-panel">
            
            <!-- Result Toolbar -->
            <div class="result-header">
                  <v-avatar rounded="lg" size="48" class="mr-4 result-thumbnail">
                    <v-img :src="result.thumbnail || 'https://via.placeholder.com/150'" cover></v-img>
                  </v-avatar>
                  <div class="result-info">
                    <h3 class="result-title">{{ result.title }}</h3>
                    <div class="result-stats">
                      <v-chip size="small" color="primary" variant="flat" class="mr-2">
                        <v-icon start size="small">mdi-clock-outline</v-icon>
                        {{ totalDuration }}
                      </v-chip>
                      <v-chip size="small" variant="outlined">
                        <v-icon start size="small">mdi-subtitles</v-icon>
                        {{ totalSegments }} segments
                      </v-chip>
                    </div>
                  </div>
                  <v-spacer></v-spacer>
                  
                  <v-menu
                    v-if="result && result.source_type === 'url'"
                    :close-on-content-click="false"
                    location="bottom end"
                  >
                    <template v-slot:activator="{ props }">
                         <v-btn 
                            v-bind="props"
                            color="secondary" 
                            variant="tonal" 
                            class="mr-2"
                            prepend-icon="mdi-youtube" 
                            @click="!videoInfo && fetchVideoInfo()"
                        >
                            Download Video
                        </v-btn>
                    </template>

                    <v-card min-width="320" class="pa-4 rounded-lg elevation-4">
                        <div class="d-flex align-center justify-space-between mb-3">
                             <div class="text-subtitle-2 font-weight-bold">Download Options</div>
                             <v-icon size="small" color="grey" @click="fetchVideoInfo" title="Refresh Info">mdi-refresh</v-icon>
                        </div>
                        
                        <div v-if="loadingFormats && !videoInfo" class="d-flex justify-center pa-4">
                            <v-progress-circular indeterminate color="primary" size="24"></v-progress-circular>
                        </div>
                        
                        <div v-else-if="videoInfo">
                            <div class="text-caption text-slate-500 mb-2 font-weight-medium text-truncate">{{ videoInfo.title }}</div>
                            

    
                            <v-checkbox 
                                v-model="downloadSubs" 
                                label="Include Subtitles (soft)" 
                                density="compact" 
                                hide-details 
                                color="primary"
                                class="mb-3"
                            ></v-checkbox>
    
                            <v-btn 
                                block 
                                color="primary" 
                                variant="tonal"
                                @click="updatePlayerQuality" 
                                :loading="isUpdatingPlayer"
                                prepend-icon="mdi-play-circle-outline"
                                class="mb-2"
                            >
                                Set for Player
                            </v-btn>

                            <v-btn 
                                block 
                                color="secondary" 
                                @click="performDownload" 
                                :loading="isDownloading"
                                variant="flat"
                                prepend-icon="mdi-download"
                            >
                                Download to Disk
                            </v-btn>
                             <div v-if="downloadStatus" class="text-center text-caption text-green mt-2 font-weight-bold">{{ downloadStatus }}</div>
                        </div>
                        <div v-else class="text-error text-caption">
                            Please check URL or internet connection.
                        </div>
                    </v-card>
                  </v-menu>

                  <v-btn icon variant="text" color="grey" @click="clearResults">
                    <v-icon>mdi-close</v-icon>
                  </v-btn>
            </div>

            <div class="result-content-wrapper flex-grow-1 overflow-hidden" style="position: relative;">
                <v-row no-gutters class="fill-height" style="min-height: 0;">
                    <!-- Video Player Column -->
                    <v-col cols="12" xl="7" class="d-flex flex-column align-center overflow-y-auto pb-6" style="padding-top: 16px; height: 100%; max-height: 100%;">
                    <div class="media-player-container-sticky">
                         <!-- Video Player -->
                         <div class="player-wrapper" v-if="mediaUrl">
                             <video
                                ref="mediaPlayer"
                                :src="mediaUrl"
                                class="media-player"
                                controls
                                preload="metadata"
                                playsinline
                                @play="handleManualPlay"
                                @pause="handleManualPause"
                                @timeupdate="checkTime"
                            ></video>
                         </div>
                    </div>

                    <!-- Separated Vocals Player (Below Video) - Collapsible -->
                    <div class="vocals-wrapper-centered mt-4 px-4" v-if="vocalsUrl && showVocalsPlayer">
                        <div class="vocals-card bg-white rounded-xl pa-4 shadow-sm border-slate-200">
                            <div 
                                class="d-flex align-center mb-3 cursor-pointer" 
                                @click="vocalsExpanded = !vocalsExpanded"
                                style="cursor: pointer;">
                                <div class="icon-box-small icon-box-primary mr-3">
                                    <v-icon size="20" color="primary">mdi-account-music</v-icon>
                                </div>
                                <div class="flex-grow-1">
                                    <div class="text-subtitle-2 font-weight-bold text-slate-700">Separated Vocals</div>
                                    <div class="text-caption text-slate-400">Isolated vocal track for better transcription</div>
                                </div>
                                <v-icon :class="{ 'rotate-180': vocalsExpanded }" class="transition-transform">
                                    mdi-chevron-down
                                </v-icon>
                            </div>
                            
                            <v-expand-transition>
                                <div v-show="vocalsExpanded">
                                    <audio
                                        :src="vocalsUrl"
                                        controls
                                        class="vocals-audio-player"
                                    ></audio>
                                </div>
                            </v-expand-transition>
                        </div>
                    </div>
                </v-col>

                <!-- Subtitle Editor Column -->
                <v-col cols="12" xl="5" class="editor-col d-flex flex-column bg-grey-lighten-5" style="height: 100%; border-left: 1px solid #e2e8f0;">

                    <!-- Subtitle Column Header -->
                    <div class="subtitle-header d-flex align-center px-4 py-3 bg-white border-b">
                        <v-icon color="primary" class="mr-2">mdi-text-box-edit-outline</v-icon>
                        <div class="text-subtitle-1 font-weight-bold text-slate-800">Subtitles</div>
                        <v-spacer></v-spacer>
                        <v-chip size="x-small" variant="flat" color="primary" class="font-weight-bold">{{ result.segments.length }} segments</v-chip>
                    </div>

                    <div class="timeline-container">
                        <div 
                        v-for="(segment, i) in result.segments" 
                        :key="i"
                        > <!-- Wrapper for card + gap -->
                            <div
                                class="timeline-card"
                                :id="'segment-' + i"
                                :class="{ 
                                    'is-playing': currentPlayingIndex === i,
                                    'is-good': segment.status === 'good'
                                }"
                            >
                        <!-- Status Strip (Modern Slim with Index) -->
                        <div class="status-strip" @click="toggleSegmentStatus(segment)" title="Click to Toggle Lock">
                           {{ i + 1 }}
                        </div>

                        <!-- Main Content -->
                        <div class="card-content pa-3">
                            
                            <!-- Header Row: Minimalist -->
                            <div class="d-flex align-center mb-2">
                                <div class="d-flex align-center mr-4">
                                    <v-btn 
                                        icon="mdi-play" 
                                        size="x-small" 
                                        variant="flat" 
                                        :color="currentPlayingIndex === i ? 'primary' : 'grey-lighten-3'"
                                        class="mr-3"
                                        rounded="circle"
                                        @click="playSegment(i)"
                                    ></v-btn>
                                </div>

                                <!-- Sleek Timing Controls with Inline Target Buttons -->
                                <div class="timing-group-modern d-flex align-center">
                                    <!-- Start Time Group -->
                                    <div class="d-flex align-center">
                                        <input
                                            type="text"
                                            class="time-input-modern"
                                            :value="formatTime(segment.start)"
                                            :readonly="segment.status === 'good'"
                                            @change="e => segment.start = parseTime(e.target.value)"
                                        />
                                        <!-- Fine-tune buttons -->
                                        <div v-if="segment.status !== 'good'" class="d-flex flex-column ml-1">
                                            <v-btn
                                                icon="mdi-chevron-up"
                                                size="x-small"
                                                variant="text"
                                                density="compact"
                                                color="grey"
                                                @click="adjustTime(segment, 'start', 0.1)"
                                                title="+100ms"
                                                style="height: 12px; width: 20px; min-width: 20px;"
                                            ></v-btn>
                                            <v-btn
                                                icon="mdi-chevron-down"
                                                size="x-small"
                                                variant="text"
                                                density="compact"
                                                color="grey"
                                                @click="adjustTime(segment, 'start', -0.1)"
                                                title="-100ms"
                                                style="height: 12px; width: 20px; min-width: 20px;"
                                            ></v-btn>
                                        </div>
                                        <v-btn
                                            v-if="segment.status !== 'good'"
                                            icon="mdi-target"
                                            size="x-small"
                                            variant="text"
                                            color="primary"
                                            @click="setCurrentTime(segment, 'start')"
                                            title="Set Start to Playhead"
                                            class="ml-1"
                                        ></v-btn>
                                        <v-btn
                                            v-if="segment.status !== 'good' && i > 0"
                                            icon="mdi-link-variant"
                                            size="x-small"
                                            variant="text"
                                            color="success"
                                            @click="snapToPrevious(i)"
                                            title="Snap to Previous Segment End"
                                            class="ml-1"
                                        ></v-btn>
                                    </div>

                                    <span class="mx-2 text-grey-lighten-1">→</span>

                                    <!-- End Time Group -->
                                    <div class="d-flex align-center">
                                        <input
                                            type="text"
                                            class="time-input-modern"
                                            :value="formatTime(segment.end)"
                                            :readonly="segment.status === 'good'"
                                            @change="e => segment.end = parseTime(e.target.value)"
                                        />
                                        <!-- Fine-tune buttons -->
                                        <div v-if="segment.status !== 'good'" class="d-flex flex-column ml-1">
                                            <v-btn
                                                icon="mdi-chevron-up"
                                                size="x-small"
                                                variant="text"
                                                density="compact"
                                                color="grey"
                                                @click="adjustTime(segment, 'end', 0.1)"
                                                title="+100ms"
                                                style="height: 12px; width: 20px; min-width: 20px;"
                                            ></v-btn>
                                            <v-btn
                                                icon="mdi-chevron-down"
                                                size="x-small"
                                                variant="text"
                                                density="compact"
                                                color="grey"
                                                @click="adjustTime(segment, 'end', -0.1)"
                                                title="-100ms"
                                                style="height: 12px; width: 20px; min-width: 20px;"
                                            ></v-btn>
                                        </div>
                                        <v-btn
                                            v-if="segment.status !== 'good'"
                                            icon="mdi-target"
                                            size="x-small"
                                            variant="text"
                                            color="secondary"
                                            @click="setCurrentTime(segment, 'end')"
                                            title="Set End to Playhead"
                                            class="ml-1"
                                        ></v-btn>
                                    </div>
                                </div>

                                <v-spacer></v-spacer>

                            <!-- Right-Aligned Tools (Delete Only) -->
                            <div v-if="segment.status !== 'good'" class="d-flex align-center gap-2">
                                <v-btn icon="mdi-delete" size="small" variant="text" color="red-lighten-1" @click="deleteSegment(i)" title="Delete Segment"></v-btn>
                            </div>
                            <div v-else class="d-flex align-center">
                                    <v-chip size="small" color="success" variant="tonal" class="font-weight-bold" prepend-icon="mdi-check">LOCKED</v-chip>
                            </div>
                        </div>

                        <!-- Text Editor (Modern) -->
                        <div class="editor-row">
                            <textarea 
                                v-model="segment.text"
                                class="native-textarea-modern"
                                :class="{ 'locked-input': segment.status === 'good' }"
                                rows="4"
                                spellcheck="false"
                                placeholder="Subtitle text..."
                                :readonly="segment.status === 'good'"
                            ></textarea>
                        </div>

                    </div>
                    </div>

                    <!-- Hover Add Zone (Inter-segment) -->
                    <div class="gap-hover-zone" @click="addSegment(i)">
                        <div class="add-indicator">
                            <v-icon size="small" color="primary">mdi-plus</v-icon>
                        </div>
                    </div>
                    </div> <!-- End of v-for wrapper -->
                    </div>
                </v-col>
            </v-row>
            </div>
            
            </div> <!-- Close results-panel -->

      </v-container>
      
      <!-- Undo Notification -->
      <v-snackbar
        v-model="showUndo"
        location="bottom left"
        timeout="-1"
        color="grey-darken-3"
        elevation="24"
        class="mb-4 ml-4"
      >
        <div class="d-flex align-center">
            <v-icon icon="mdi-history" start size="small" class="mr-2"></v-icon>
            {{ undoMessage }}
        </div>
        
        <template v-slot:actions>
          <v-btn
            color="yellow-accent-2"
            variant="text"
            @click="performUndo"
            class="font-weight-bold"
          >
            UNDO
          </v-btn>
          <v-btn
            color="white"
            variant="text"
            icon="mdi-close"
            size="small"
            @click="showUndo = false"
          ></v-btn>
        </template>
      </v-snackbar>

      <!-- Save Project Dialog -->
      <v-dialog v-model="showSaveDialog" max-width="500">
        <v-card rounded="xl">
          <v-card-title class="d-flex align-center pa-6 bg-primary">
            <v-icon class="mr-3" color="white">mdi-content-save</v-icon>
            <span class="text-h6 font-weight-bold text-white">Save Project</span>
          </v-card-title>

          <v-card-text class="pa-6">
            <div class="text-body-1 mb-4">
              Save your subtitle project with timings and metadata.
            </div>

            <!-- Only show video download option for URL-based projects -->
            <div v-if="inputType === 'url' && url" class="mt-4">
              <v-checkbox
                v-model="saveWithVideo"
                color="primary"
                hide-details
              >
                <template v-slot:label>
                  <div>
                    <div class="font-weight-bold">Also download video file</div>
                    <div class="text-caption text-grey">Saves video to downloads folder</div>
                  </div>
                </template>
              </v-checkbox>


            </div>

            <!-- Info for uploaded files -->
            <div v-else class="mt-4 pa-4 bg-grey-lighten-4 rounded-lg">
              <div class="d-flex align-center">
                <v-icon color="info" class="mr-2">mdi-information</v-icon>
                <div class="text-caption">
                  Keep your video file in the same folder as the project JSON for easy reloading.
                </div>
              </div>
            </div>
          </v-card-text>

          <v-card-actions class="pa-6 pt-0">
            <v-spacer></v-spacer>
            <v-btn
              variant="text"
              @click="showSaveDialog = false"
            >
              Cancel
            </v-btn>
            <v-btn
              color="primary"
              variant="flat"
              @click="performSave"
              prepend-icon="mdi-content-save"
            >
              Save Project
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

    </v-main>
  </v-app>
</template>

<style scoped>
/* ============================================
   DESIGN SYSTEM
   ============================================ */
.app-bg {
  background: #f8fafc;
  min-height: 100vh;
}

.full-height-container {
    height: 100%;
    display: flex;
    flex-direction: column;
}

/* ============================================
   HERO HEADER
   ============================================ */
.hero-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 32px;
  background: linear-gradient(135deg, #FF4B4B 0%, #FF6B6B 50%, #FF8585 100%);
  border-radius: 20px;
  box-shadow: 0 10px 30px rgba(255, 75, 75, 0.25);
}

.hero-icon {
  width: 56px;
  height: 56px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(10px);
}

.app-logo {
    /* Clean presentation */
    filter: drop-shadow(0 4px 6px rgba(0,0,0,0.05));
    transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.app-logo:hover {
    transform: scale(1.05); /* Subtle scale without rotation */
}

.hero-title {
  font-size: 1.75rem;
  font-weight: 800;
  color: white;
  letter-spacing: -0.5px;
  margin: 0;
}

.hero-subtitle {
  color: rgba(255, 255, 255, 0.85);
  font-size: 0.9rem;
  margin: 0;
  font-weight: 500;
}

.export-btn {
  font-weight: 700;
  letter-spacing: 0.3px;
  color: #FF4B4B;
  padding: 0 24px;
}

/* --- Modern Sidebar Styling --- */
.modern-sidebar {
    background-color: #ffffff; /* or #f8fafc effectively */
    border-right: 1px solid #f1f5f9;
}
.sidebar-header {
    background: #ffffff;
}

/* Typography Utilities */
.text-slate-800 { color: #1e293b !important; }
.text-slate-700 { color: #334155 !important; }
.text-slate-500 { color: #64748b !important; }
.text-slate-400 { color: #94a3b8 !important; }
.text-indigo-500 { color: #6366f1 !important; }
.bg-slate-100 { background-color: #f1f5f9 !important; }
.bg-indigo-50 { background-color: #eef2ff !important; }
.tracking-tight { letter-spacing: -0.5px; }

/* Components */
.logo-box {
    filter: drop-shadow(0 4px 6px rgba(0,0,0,0.05));
    transition: transform 0.2s;
}
.logo-box:hover {
    transform: scale(1.05);
}

.source-toggle-wrapper {
    padding: 6px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}
.toggle-pill {
    text-transform: none !important;
    font-weight: 700 !important;
    letter-spacing: 0 !important;
    color: #64748b !important;
}
.toggle-pill.v-btn--active {
    color: #ffffff !important;
    background: #FF4B4B !important; /* Force Primary Red */
    box-shadow: 0 4px 12px rgba(255, 75, 75, 0.3);
}

.divider-label {
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 1px;
    color: #cbd5e1;
}

/* Workflow Card */
.workflow-card {
    border: 1px solid #e2e8f0;
    transition: all 0.2s;
}
.workflow-card:hover {
    border-color: #cbd5e1;
    box-shadow: 0 10px 30px rgba(0,0,0,0.03);
}

.icon-box-small {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.icon-box-primary {
    background-color: #fff1f2;
    color: #FF4B4B;
}

/* Inputs */
.modern-input .v-field {
    border-radius: 12px !important;
}
.modern-input .v-field__overlay {
    border-radius: 12px !important;
}
.modern-input .v-field__outline__start,
.modern-input .v-field__outline__end,
.modern-input .v-field__outline__notch {
    border-color: #e2e8f0 !important;
}
.modern-input .v-field--focused .v-field__outline__start,
.modern-input .v-field--focused .v-field__outline__end,
.modern-input .v-field--focused .v-field__outline__notch {
    border-color: #6366f1 !important;
    border-width: 2px;
}
.modern-input .v-field__input {
    min-height: 48px !important;
    padding-top: 10px !important;
    padding-bottom: 10px !important;
}

/* Custom Tooltip High Visibility - Global Override */
.v-overlay__content.custom-tooltip {
    background-color: #0f172a !important; /* Dark Slate */
    color: white !important;
    font-size: 0.85rem !important;
    line-height: 1.5 !important;
    border: 1px solid #334155;
    border-radius: 8px !important;
    box-shadow: 0 10px 25px rgba(0,0,0,0.25) !important;
    opacity: 1 !important;
    padding: 0 !important;
    pointer-events: none;
}
.custom-tooltip > div {
    padding: 12px;
}

/* Script Editor */
.editor-box {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    overflow: hidden;
    background: #f8fafc;
}
.editor-box:focus-within {
    background: white;
    border-color: #6366f1;
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
.styled-textarea {
    width: 100%;
    padding: 12px;
    border: none;
    outline: none;
    resize: none;
    font-size: 0.9rem;
    line-height: 1.6;
    color: #334155;
    background: transparent;
}
.editor-footer {
    padding: 4px 12px;
    font-size: 0.7rem;
    color: #94a3b8;
    background: #f1f5f9;
    border-top: 1px solid #e2e8f0;
    text-align: right;
}

/* Action Button */
.main-action-btn {
    background: linear-gradient(135deg, #FF4B4B 0%, #FF6B6B 100%);
    color: white !important;
    text-transform: none;
    font-weight: 700;
    font-size: 1.1rem;
    letter-spacing: 0.5px;
    box-shadow: 0 10px 20px rgba(255, 75, 75, 0.3);
}
.main-action-btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 15px 30px rgba(255, 75, 75, 0.4);
}


/* Empty State */
/* Empty State */
.empty-state-wrapper {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    min-height: 400px; /* Minimal height safeguard */
}
.empty-state, .loading-state {
  text-align: center;
  padding: 48px;
  background: white;
  border-radius: 24px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.05);
  max-width: 600px;
}
.empty-icon {
  width: 120px;
  height: 120px;
  background: #f1f5f9;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 24px auto;
}
.empty-title, .loading-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 12px;
}
.empty-desc, .loading-desc {
  color: #64748b;
  line-height: 1.6;
}

/* Results Panel */
.results-panel {
  background: white;
  border-radius: 20px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden; 
  height: calc(100vh - 200px); /* Fit to screen with margin */
  margin-bottom: 0;
}
.result-header {
  padding: 16px 24px;
  background: white;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 10;
}
.result-title {
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 4px;
  max-width: 500px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.result-stats {
    display: flex;
    align-items: center;
}

/* Custom Tooltip High Visibility */
.custom-tooltip {
    background-color: #1e293b !important; /* Dark Slate Blue */
    color: white !important;
    font-size: 0.85rem !important;
    line-height: 1.5 !important;
    border: 1px solid #334155;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
    opacity: 1 !important;
}

/* Media Player Container */
.media-player-container-sticky {
    width: 95%; /* Use 95% to leave breathing room */
    max-width: 950px; /* Balanced size to fit vocals below */
    padding: 0;
    display: flex;
    justify-content: center;
    margin-bottom: 20px;
}

.player-wrapper {
    /* YouTube-style video container */
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    width: 100%;
    aspect-ratio: 16 / 9; /* Maintain 16:9 aspect ratio */
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: #000;
    position: relative;
}

.media-player {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: contain; /* Maintains aspect ratio, centers, adds letterbox/pillarbox */
}

/* Timeline Container (Independent Scroll) */
.timeline-container {
    padding: 16px;
    height: 100%;
    overflow-y: auto; 
    padding-bottom: 200px;
    /* Custom Scrollbar for Webkit */
    scrollbar-width: thin;
    scrollbar-color: #cbd5e1 transparent;
}
.timeline-container::-webkit-scrollbar {
    width: 6px;
}
.timeline-container::-webkit-scrollbar-thumb {
    background-color: #cbd5e1;
    border-radius: 3px;
}

.timeline-card {
    display: flex;
    background: white;
    border-radius: 12px;
    margin-bottom: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    overflow: hidden;
    transition: all 0.2s ease;
    border: 1px solid transparent;
}

/* Inter-segment Add Button */
.gap-hover-zone {
    height: 16px; /* Small gap normally */
    margin: 4px 0;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s;
    opacity: 0;
}
.gap-hover-zone:hover {
    height: 32px; /* Expands on hover */
    opacity: 1;
}
.add-indicator {
    width: 28px;
    height: 28px;
    background: #eef2ff;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #6366f1;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    border: 1px solid #c7d2fe;
}

.timeline-card:hover {
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

.timeline-card.is-playing {
    border-color: #FF4B4B;
    background: #fffafa;
}

.timeline-card.is-good {
    border-color: #4CAF50;
}

.status-strip {
    width: 32px; /* Wider for number */
    background: #f1f5f9;
    color: #94a3b8;
    cursor: pointer;
    flex-shrink: 0;
    transition: all 0.3s;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    border-right: 1px solid #e2e8f0;
}
.status-strip:hover {
    background: #e2e8f0;
    color: #64748b;
}
.timeline-card.is-good .status-strip {
    background: #4CAF50;
    color: white;
    border-color: #4CAF50;
}

/* Modern Input Styles */
.time-input-modern {
    border: none;
    background: #f1f5f9;
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: #334155;
    width: 90px;
    text-align: center;
    padding: 2px 0;
    transition: all 0.2s;
}
.time-input-modern:focus {
    background: white;
    color: #FF4B4B;
    box-shadow: 0 0 0 2px rgba(255, 75, 75, 0.2);
    outline: none;
}
.native-textarea-modern {
    width: 100%;
    border: 1px solid transparent; 
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 0.95rem;
    line-height: 1.6;
    background: #f8fafc;
    transition: all 0.2s;
    resize: none;
}
.native-textarea-modern:focus {
    background: white;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
    border-color: #e2e8f0;
    outline: none;
}
.native-textarea-modern.locked-input {
    background: #f1f5f9;
    color: #64748b;
    cursor: default;
}

/* Overwrite old cards */
.card-content {
    flex: 1;
    min-width: 0;
}

.time-pill {
    display: flex;
    align-items: center;
    position: relative;
    padding: 0 4px;
    background: white; /* distinct background for pill */
    border-radius: 6px;
    border: 1px solid transparent;
    transition: all 0.2s;
}
.time-pill:hover {
    border-color: #cbd5e1;
}

.time-label {
    font-size: 0.65rem;
    font-weight: 800;
    color: #94a3b8;
    margin-right: 8px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

.time-input-native {
    border: none;
    background: transparent;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 0.95rem; /* Slightly larger text */
    font-weight: 600;
    color: #334155;
    width: 110px; /* Increased to prevent overlap */
    text-align: center;
    outline: none;
    padding: 4px 0;
    margin-right: 4px; /* Space for buttons */
}
.time-input-native:focus {
    color: #FF4B4B;
    background: rgba(255, 75, 75, 0.05);
    border-radius: 4px;
}

.time-actions {
    display: flex;
    align-items: center;
    gap: 2px; /* Space between target and arrows */
}
/* Ensure buttons don't shrink */
.time-actions .v-btn {
    flex-shrink: 0;
}

.nudge-btns {
    display: flex;
    flex-direction: column;
    justify-content: center;
    height: 24px;
}
.nudge-btns .v-btn {
    height: 12px !important;
    width: 20px !important;
    min-width: 0 !important;
    padding: 0 !important;
}

.native-textarea {
    width: 100%;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 12px;
    font-size: 1rem;
    line-height: 1.6;
    background: #fff;
    resize: vertical;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
    font-family: inherit;
    color: #1e293b;
}
.native-textarea:focus {
    border-color: #FF4B4B;
    box-shadow: 0 0 0 3px rgba(255, 75, 75, 0.1);
}

/* Locked State */
.timeline-card.is-good .time-input-native {
    color: #4CAF50;
    opacity: 0.8;
}
.locked-input {
    background: #f8fafc;
    color: #64748b;
    border-color: #f1f5f9;
    font-style: italic;
    cursor: default;
}
.locked-input:focus {
    border-color: #e2e8f0;
    box-shadow: none;
}
.locked-group {
    border-color: #4CAF50;
    background: #f0fdf4;
}

.segment-tools {
    display: flex;
    gap: 4px;
    opacity: 0.6;
    transition: opacity 0.2s;
}
.timeline-card:hover .segment-tools {
    opacity: 1;
}

.locked-badge {
    display: flex;
    align-items: center;
    background: #f0fdf4;
    padding: 4px 8px;
    border-radius: 6px;
    border: 1px solid #dcfce7;
}

/* Raw Segments */
.raw-segments-panel {
    margin-top: 32px;
    border-top: 2px dashed #e2e8f0;
    padding-top: 20px;
}
.raw-list {
    max-height: 300px;
    overflow-y: auto;
    background: #f8fafc;
    border-radius: 8px;
    padding: 8px;
}
.raw-segment-item {
    padding: 6px 8px;
    border-bottom: 1px solid #e2e8f0;
    font-size: 0.8rem;
    color: #64748b;
    display: flex;
}
.raw-time {
    font-family: monospace;
    font-weight: 600;
    margin-right: 12px;
    color: #475569;
}

/* Process Button */
.process-btn {
    height: 56px;
    font-weight: 700;
    border-radius: 12px;
    font-size: 1rem;
    letter-spacing: 0.5px;
}
/* Modern Switch Opacity Fix */
.modern-switch.v-input--is-label-active .v-selection-control__input > .v-switch__track {
    opacity: 1 !important;
    background-color: #FF4B4B !important;
}
.modern-switch .v-selection-control__input > .v-switch__track {
    opacity: 1 !important;
    background-color: #cbd5e1 !important; /* OFF state gray */
}

/* Vocals Audio Player */
.vocals-wrapper {
    max-width: 600px;
    width: 100%;
}

.vocals-wrapper-centered {
    max-width: 750px;
    width: 100%;
    display: flex;
    justify-content: center;
}

.vocals-card {
    border: 1px solid #e2e8f0;
    width: 100%;
}

.vocals-audio-player {
    width: 100%;
    height: 48px;
    border-radius: 8px;
    outline: none;
}

.vocals-audio-player::-webkit-media-controls-panel {
    background-color: #f8fafc;
    border-radius: 8px;
}

/* Chevron rotation animation */
.transition-transform {
    transition: transform 0.3s ease;
}

.rotate-180 {
    transform: rotate(180deg);
}

</style>
