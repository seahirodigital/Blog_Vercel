// Web Worker用のコードを文字列として定義
const workerCode = `
    let audioContext = null;
    let reader = null;

    self.onmessage = (e) => {
        const { file, chunkIndex, chunkSize } = e.data;

        if (!audioContext) {
            audioContext = new (self.AudioContext || self.webkitAudioContext)();
        }

        const start = chunkIndex * chunkSize;
        const end = Math.min(start + chunkSize, file.size);

        if (start >= file.size) {
            self.postMessage({ type: 'done' });
            return;
        }
        
        reader = new FileReader();
        reader.onload = (event) => {
            audioContext.decodeAudioData(event.target.result)
                .then(buffer => {
                    const channelData = buffer.getChannelData(0);
                    self.postMessage({
                        type: 'data',
                        chunkIndex: chunkIndex,
                        channelData: channelData,
                        sampleRate: buffer.sampleRate,
                        duration: buffer.duration,
                    }, [channelData.buffer]);
                })
                .catch(err => {
                    self.postMessage({ type: 'error', message: '音声チャンクのデコードに失敗: ' + err.message });
                });
        };
        reader.onerror = () => {
            self.postMessage({ type: 'error', message: 'ファイルチャンクの読み込みに失敗' });
        };

        const blob = file.slice(start, end);
        reader.readAsArrayBuffer(blob);
    };
`;

let currentFile = null;
let audioContext = null;
let currentAudioBuffer = null;
let waveformData = null; 
let clips = [];
let selectedClipIndex = -1;
let videoElement = null;
let canvasElement = null;
let isDragging = false;
let isResizing = false;
let resizeDirection = null;
let dragStartX = 0;
let zoomLevel = 1;
let scrollOffset = 0;
let dragMoved = false;
let checkedClips = new Set();
let undoStack = [];
let maxUndoSteps = 50;
let isWaveformDragging = false;
let waveformDragStartX = 0;
let waveformDragStartScroll = 0;
let isProcessing = false;
let outputDirectory = null;
let hoveredClipIndex = -1;
let audioWorker = null;

function init() {
  const blob = new Blob([workerCode], { type: 'application/javascript' });
  audioWorker = new Worker(URL.createObjectURL(blob));

  videoElement = document.getElementById('videoPlayer');
  canvasElement = document.getElementById('waveformCanvas');
  
  document.getElementById('fileInput').addEventListener('change', handleFileSelect);
  document.getElementById('outputDirInput').addEventListener('change', handleOutputDirSelect);
  document.getElementById('quietThreshold').addEventListener('input', updateThresholdDisplays);
  document.getElementById('loudThreshold').addEventListener('input', updateThresholdDisplays);
  document.getElementById('analyzeBtn').addEventListener('click', handleAnalyze);
  document.getElementById('downloadSegmentsBtn').addEventListener('click', handleDownloadSegments);
  document.getElementById('addClipBtn').addEventListener('click', handleAddClip);
  document.getElementById('deleteClipBtn').addEventListener('click', handleDeleteClip);
  document.getElementById('timelineAddBtn').addEventListener('click', handleAddClip);
  document.getElementById('timelineRemoveBtn').addEventListener('click', handleDeleteClip);
  
  canvasElement.addEventListener('click', handleCanvasClick);
  canvasElement.addEventListener('wheel', handleWheel, { passive: false });
  canvasElement.addEventListener('mousedown', handleWaveformMouseDown);
  
  document.addEventListener('mousemove', handleMouseMove);
  document.addEventListener('mouseup', handleMouseUp);
  document.addEventListener('keydown', handleKeyDown);
  document.addEventListener('keyup', handleKeyUp);
  
  addMessage('Movie_AutoCutへようこそ', 'info');
  addMessage('動画ファイルを選択してください', 'info');
}

function handleOutputDirSelect(e) {
  const files = e.target.files;
  if (files.length > 0) {
    outputDirectory = files[0].webkitRelativePath.split('/')[0];
    document.getElementById('outputDirDisplay').textContent = '保存先: ' + outputDirectory;
    addMessage('保存先を設定しました: ' + outputDirectory, 'success');
  }
}

function handleKeyDown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;

  switch (e.key) {
    case ' ':
    case 'Spacebar':
      if (!e.repeat) {
        e.preventDefault();
        videoElement.paused ? videoElement.play() : videoElement.pause();
      }
      break;
      
    case 'ArrowLeft':
      e.preventDefault();
      videoElement.currentTime = Math.max(0, videoElement.currentTime - 5);
      break;
      
    case 'ArrowRight':
      e.preventDefault();
      videoElement.currentTime = Math.min(videoElement.duration, videoElement.currentTime + 5);
      break;
      
    case 'p':
    case 'P':
      e.preventDefault();
      handleAddClip();
      break;
      
    case 'Backspace':
    case 'Delete':
      e.preventDefault();
      if (hoveredClipIndex !== -1) {
        deleteSingleClip(hoveredClipIndex);
        hoveredClipIndex = -1;
      } else {
        handleDeleteClip();
      }
      break;
      
    case 'z':
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        handleUndo();
      }
      break;
  }
}

function handleKeyUp(e) {
  // 将来的な機能拡張のために残しておく
}

function saveState() {
  undoStack.push({
    clips: JSON.parse(JSON.stringify(clips)),
    checkedClips: new Set(checkedClips),
    selectedClipIndex: selectedClipIndex
  });
  
  if (undoStack.length > maxUndoSteps) undoStack.shift();
}

function handleUndo() {
  if (undoStack.length === 0) {
    addMessage('これ以上元に戻せません', 'warning');
    return;
  }
  
  const state = undoStack.pop();
  clips = JSON.parse(JSON.stringify(state.clips));
  checkedClips = new Set(state.checkedClips);
  selectedClipIndex = state.selectedClipIndex;
  
  renderClips();
  updateClipList();
  addMessage('元に戻しました', 'success');
}

function handleWheel(e) {
  if (e.shiftKey) {
    e.preventDefault();
    
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    zoomLevel = Math.max(1, Math.min(zoomLevel * delta, 200));
    
    if (currentAudioBuffer) {
      const duration = currentAudioBuffer.duration;
      const maxScroll = duration * (1 - 1/zoomLevel);
      scrollOffset = Math.max(0, Math.min(scrollOffset, maxScroll));
      
      drawWaveform();
      renderClips();
    }
    
    addMessage('ズーム: ' + Math.round(zoomLevel * 100) + '%', 'info');
  }
}

function handleFileSelect(e) {
    const file = e.target.files[0];
    if (!file) return;

    currentAudioBuffer = null;
    waveformData = null;
    clips = [];
    renderClips();
    updateClipList();
    drawWaveform();
    document.getElementById('fileInput').disabled = true;
    document.getElementById('analyzeBtn').disabled = true;

    currentFile = file;
    if (videoElement.src) {
        URL.revokeObjectURL(videoElement.src);
    }
    videoElement.src = URL.createObjectURL(file);
    videoElement.load();
    
    addMessage('ファイルを読み込みました: ' + file.name, 'success');
    addMessage('音声データを解析しています... これには数分かかる場合があります。', 'info');
    document.getElementById('progressContainer').style.display = 'block';
    updateProgress('音声データを解析中...', 0);
    
    try {
        const fileReader = new FileReader();
        fileReader.onload = (e) => {
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            audioContext.decodeAudioData(e.target.result).then(buffer => {
                currentAudioBuffer = buffer;
                
                const channelData = currentAudioBuffer.getChannelData(0);
                const sampleRate = currentAudioBuffer.sampleRate;
                const interval = Math.floor(sampleRate / 100);
                waveformData = [];
                for (let i = 0; i < channelData.length; i += interval) {
                    let max = 0.0;
                    for (let j = 0; j < interval && i + j < channelData.length; j++) {
                         if (Math.abs(channelData[i+j]) > max) max = Math.abs(channelData[i+j]);
                    }
                    waveformData.push(max);
                }
                
                updateProgress('解析完了', 100);
                setTimeout(() => document.getElementById('progressContainer').style.display = 'none', 1000);
                addMessage('音声波形を表示しました', 'success');
                drawWaveform();

                document.getElementById('fileInput').disabled = false;
                document.getElementById('analyzeBtn').disabled = false;
            }).catch(err => {
                 addMessage(`音声解析エラー: ${err.message}`, 'error');
                 document.getElementById('fileInput').disabled = false;
                 document.getElementById('analyzeBtn').disabled = false;
            });
        };
        fileReader.onprogress = (e) => {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                updateProgress('ファイルを読み込み中...', percentComplete);
            }
        };
        fileReader.readAsArrayBuffer(file);
    } catch(err) {
        addMessage(`エラー: ${err.toString()}`, 'error');
        document.getElementById('fileInput').disabled = false;
        document.getElementById('analyzeBtn').disabled = false;
    }
}

function updateThresholdDisplays() {
  const quietValue = document.getElementById('quietThreshold').value;
  const loudValue = document.getElementById('loudThreshold').value;
  document.getElementById('quietThresholdValue').textContent = quietValue;
  document.getElementById('loudThresholdValue').textContent = loudValue;
  
  if (parseInt(quietValue) > parseInt(loudValue)) {
    addMessage('注意: 静かな音の閾値が大きな音の閾値より大きくなっています', 'warning');
  }
}

function drawWaveform() {
    const ctx = canvasElement.getContext('2d');
    const width = canvasElement.width = canvasElement.offsetWidth * 2;
    const height = canvasElement.height = 160;
    ctx.clearRect(0, 0, width, height);

    if (!waveformData || !currentAudioBuffer) return;

    const duration = currentAudioBuffer.duration;
    const viewDuration = duration / zoomLevel;
    const viewStart = scrollOffset;
    
    const startIndex = Math.floor((viewStart / duration) * waveformData.length);
    const endIndex = Math.floor(((viewStart + viewDuration) / duration) * waveformData.length);
    const viewData = waveformData.slice(startIndex, endIndex);

    const amp = height / 2;
    ctx.fillStyle = 'rgba(139,92,246,0.3)';

    for (let i = 0; i < width; i++) {
        const dataIndex = Math.floor((i / width) * viewData.length);
        const datum = viewData[dataIndex] || 0;
        const h = datum * amp;
        ctx.fillRect(i, amp - h, 1, h * 2);
    }
}

function calculateRMS(channelData, startSample, endSample) {
  let sum = 0;
  const count = endSample - startSample;
  if (count <= 0) return 0;
  
  for (let i = startSample; i < endSample; i++) {
    const val = channelData[i] || 0;
    sum += val * val;
  }
  
  return Math.sqrt(sum / count);
}

function detectVolumeSpikes(audioBuffer, quietThresholdDb, loudThresholdDb, lookbackTime, minGap) {
  const channelData = audioBuffer.getChannelData(0);
  const sampleRate = audioBuffer.sampleRate;
  const quietThreshold = Math.pow(10, quietThresholdDb / 20);
  const loudThreshold = Math.pow(10, loudThresholdDb / 20);
  const lookbackSamples = lookbackTime * sampleRate;
  const minGapSamples = minGap * sampleRate;
  const windowSize = sampleRate * 0.1;
  
  const spikeMoments = [];
  let lastDetectionSample = -minGapSamples * 2;
  
  for (let i = lookbackSamples; i < channelData.length - windowSize; i += windowSize) {
    const currentRMS = calculateRMS(channelData, i, i + windowSize);
    const pastStartSample = Math.max(0, i - lookbackSamples);
    const pastRMS = calculateRMS(channelData, pastStartSample, pastStartSample + windowSize);
    
    if (pastRMS < quietThreshold && currentRMS > loudThreshold && (i - lastDetectionSample) > minGapSamples) {
      spikeMoments.push(i / sampleRate);
      lastDetectionSample = i;
    }
  }
  
  return spikeMoments;
}

function handleAnalyze() {
  if (!currentAudioBuffer) {
    addMessage('先に動画ファイルを選択し、音声解析が完了するまでお待ちください。', 'error');
    return;
  }
  
  const quietThreshold = parseInt(document.getElementById('quietThreshold').value);
  const loudThreshold = parseInt(document.getElementById('loudThreshold').value);
  const lookbackTime = parseFloat(document.getElementById('lookbackTime').value);
  const minGap = parseFloat(document.getElementById('minGap').value);
  const clipDuration = parseFloat(document.getElementById('clipDuration').value);
  
  if (quietThreshold > loudThreshold) {
    addMessage('エラー: 静かな音の閾値は大きな音の閾値より小さくしてください', 'error');
    return;
  }
  
  document.getElementById('analyzeBtn').disabled = true;
  document.getElementById('progressContainer').style.display = 'block';
  updateProgress('解析中...', 50);
  
  addMessage('音の急激な変化を検出しています...', 'info');
  
  setTimeout(() => {
    const duration = currentAudioBuffer.duration;
    const spikeMoments = detectVolumeSpikes(currentAudioBuffer, quietThreshold, loudThreshold, lookbackTime, minGap);
    
    clips = [];
    for (const startTime of spikeMoments) {
      const endTime = Math.min(startTime + clipDuration, duration);
      if (endTime - startTime > 0.5) {
        clips.push({ start: startTime, end: endTime });
      }
    }
    
    addMessage(spikeMoments.length + '個の音量急変位置を検出', 'success');
    addMessage(clips.length + '個のクリップを作成しました', 'success');
    
    renderClips();
    updateClipList();
    
    document.getElementById('downloadSegmentsBtn').style.display = 'inline-block';
    document.getElementById('clipEditSection').style.display = 'block';
    
    updateProgress('解析完了', 100);
    
    setTimeout(() => {
      document.getElementById('analyzeBtn').disabled = false;
      document.getElementById('progressContainer').style.display = 'none';
    }, 1000);
  }, 100);
}

function renderClips() {
  if (!currentAudioBuffer) return;
  
  const markersDiv = document.getElementById('segmentMarkers');
  markersDiv.innerHTML = '';
  const duration = currentAudioBuffer.duration;
  const viewDuration = duration / zoomLevel;
  const viewStart = scrollOffset;
  const viewEnd = viewStart + viewDuration;
  
  clips.forEach((clip, index) => {
    if (clip.end < viewStart || clip.start > viewEnd) return;
    
    const relativeStart = Math.max(0, clip.start - viewStart);
    const relativeEnd = Math.min(viewDuration, clip.end - viewStart);
    
    const startPercent = (relativeStart / viewDuration) * 100;
    const widthPercent = ((relativeEnd - relativeStart) / viewDuration) * 100;
    
    if (startPercent >= 100 || startPercent + widthPercent <= 0) return;
    
    const marker = document.createElement('div');
    marker.className = 'segment-marker';
    if (index === selectedClipIndex) marker.classList.add('selected');
    if (checkedClips.has(index)) marker.classList.add('checked');
    marker.style.left = startPercent + '%';
    marker.style.width = widthPercent + '%';
    marker.dataset.index = index;
    
    const popup = document.createElement('div');
    popup.className = 'segment-info-popup';
    
    const startTimeStr = formatTimeForPopup(clip.start);
    const endTimeStr = formatTimeForPopup(clip.end);
    const durationStr = (clip.end - clip.start).toFixed(2) + '秒';
    popup.innerHTML = `${startTimeStr}<br>　│<br>${endTimeStr} (${durationStr})`;
    marker.appendChild(popup);
    
    const leftHandle = document.createElement('div');
    leftHandle.className = 'resize-handle left';
    leftHandle.dataset.direction = 'left';
    leftHandle.dataset.index = index;
    marker.appendChild(leftHandle);
    
    const rightHandle = document.createElement('div');
    rightHandle.className = 'resize-handle right';
    rightHandle.dataset.direction = 'right';
    rightHandle.dataset.index = index;
    marker.appendChild(rightHandle);
    
    marker.addEventListener('mousedown', handleMarkerMouseDown);
    marker.addEventListener('mouseenter', () => {
        hoveredClipIndex = index;
    });
    marker.addEventListener('mouseleave', () => {
        hoveredClipIndex = -1;
    });
    leftHandle.addEventListener('mousedown', handleResizeMouseDown);
    rightHandle.addEventListener('mousedown', handleResizeMouseDown);
    
    markersDiv.appendChild(marker);
  });
}

function handleWaveformMouseDown(e) {
  if (e.target.classList.contains('segment-marker') || e.target.classList.contains('resize-handle')) return;
  
  isWaveformDragging = true;
  waveformDragStartX = e.clientX;
  waveformDragStartScroll = scrollOffset;
  canvasElement.style.cursor = 'grabbing';
  document.getElementById('overviewPopup').style.display = 'block';
  updateOverviewPopup();
  e.preventDefault();
}

function handleMarkerMouseDown(e) {
  if (e.target.classList.contains('resize-handle')) return;
  
  const index = parseInt(e.currentTarget.dataset.index);
  
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    checkedClips.has(index) ? checkedClips.delete(index) : checkedClips.add(index);
    selectedClipIndex = index;
    renderClips();
    updateClipList();
    return;
  }
  
  checkedClips.has(index) ? checkedClips.delete(index) : checkedClips.add(index);
  selectedClipIndex = index;
  isDragging = true;
  dragMoved = false;
  dragStartX = e.clientX;
  
  renderClips();
  updateClipList();
  e.preventDefault();
}

function handleResizeMouseDown(e) {
  const index = parseInt(e.currentTarget.dataset.index);
  const direction = e.currentTarget.dataset.direction;
  
  selectedClipIndex = index;
  isResizing = true;
  resizeDirection = direction;
  dragStartX = e.clientX;
  
  e.stopPropagation();
  e.preventDefault();
}

function handleMouseMove(e) {
  if (!currentAudioBuffer) return;
  
  const rect = canvasElement.getBoundingClientRect();
  const duration = currentAudioBuffer.duration;
  const viewDuration = duration / zoomLevel;
  
  if (isWaveformDragging) {
    const pixelDelta = e.clientX - waveformDragStartX;
    const timeDelta = (pixelDelta / rect.width) * viewDuration;
    scrollOffset = waveformDragStartScroll - timeDelta;
    const maxScroll = duration * (1 - 1/zoomLevel);
    scrollOffset = Math.max(0, Math.min(scrollOffset, maxScroll));
    
    drawWaveform();
    renderClips();
    updateOverviewPopup();
    return;
  }

  const deltaX = e.clientX - dragStartX;
  const deltaTime = (deltaX / rect.width) * viewDuration;
  
  if (isDragging && selectedClipIndex >= 0) {
    if (Math.abs(deltaX) > 3) dragMoved = true;
    
    const clip = clips[selectedClipIndex];
    const clipDuration = clip.end - clip.start;
    
    let newStart = clip.start + deltaTime;
    newStart = Math.max(0, Math.min(newStart, duration - clipDuration));
    
    clips[selectedClipIndex] = { start: newStart, end: newStart + clipDuration };
    
    if (videoElement) videoElement.currentTime = newStart;
    
    dragStartX = e.clientX;
    renderClips();
    updateClipList();
  } else if (isResizing && selectedClipIndex >= 0) {
    const clip = clips[selectedClipIndex];
    
    if (resizeDirection === 'left') {
      let newStart = clip.start + deltaTime;
      newStart = Math.max(0, Math.min(newStart, clip.end - 0.5));
      clips[selectedClipIndex].start = newStart;
      if (videoElement) videoElement.currentTime = newStart;
    } else if (resizeDirection === 'right') {
      let newEnd = clip.end + deltaTime;
      newEnd = Math.max(clip.start + 0.5, Math.min(newEnd, duration));
      clips[selectedClipIndex].end = newEnd;
      if (videoElement) videoElement.currentTime = newEnd;
    }
    
    dragStartX = e.clientX;
    renderClips();
    updateClipList();
  }
}

function handleMouseUp(e) {
  if (isWaveformDragging) {
    isWaveformDragging = false;
    canvasElement.style.cursor = 'grab';
    document.getElementById('overviewPopup').style.display = 'none';
    return;
  }
  
  if (isDragging || isResizing) {
    if (isDragging && !dragMoved && selectedClipIndex >= 0) {
      videoElement.currentTime = clips[selectedClipIndex].start;
    }
    
    isDragging = false;
    isResizing = false;
    resizeDirection = null;
    dragMoved = false;
  }
}

function updateOverviewPopup() {
    if (!currentAudioBuffer) return;
    const thumb = document.getElementById('overviewThumb');
    const totalDuration = currentAudioBuffer.duration;
    const viewDuration = totalDuration / zoomLevel;

    const leftPercent = (scrollOffset / totalDuration) * 100;
    const widthPercent = (viewDuration / totalDuration) * 100;

    thumb.style.left = `${leftPercent}%`;
    thumb.style.width = `${widthPercent}%`;
}

function updateClipList() {
  const clipList = document.getElementById('clipList');
  clipList.innerHTML = '';
  
  if (clips.length === 0) {
    clipList.innerHTML = '<p style="grid-column:1/-1;text-align:center;color:#9ca3af;padding:20px">クリップがありません</p>';
    return;
  }
  
  clips.forEach((clip, index) => {
    const item = document.createElement('div');
    item.className = 'clip-item';
    if (checkedClips.has(index)) item.classList.add('checked');
    
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'clip-checkbox';
    checkbox.checked = checkedClips.has(index);
    
    const infoDiv = document.createElement('div');
    infoDiv.className = 'clip-item-info';
    infoDiv.innerHTML = '<strong>クリップ ' + (index + 1) + '</strong><br><span style="color:#10b981;font-size:0.85rem">' + formatTime(clip.start) + ' → ' + formatTime(clip.end) + ' (' + formatTime(clip.end - clip.start) + ')</span>';
    
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'clip-item-actions';
    actionsDiv.innerHTML = '<button class="btn-small" style="background:#8b5cf6;color:white" onclick="playClip(' + index + ')">▶️</button><button class="btn-small" style="background:#ef4444;color:white" onclick="deleteSingleClip(' + index + ')">🗑️</button>';
    
    item.appendChild(checkbox);
    item.appendChild(infoDiv);
    item.appendChild(actionsDiv);
    
    item.addEventListener('click', (e) => {
      if (!e.target.classList.contains('btn-small')) {
        checkedClips.has(index) ? checkedClips.delete(index) : checkedClips.add(index);
        renderClips();
        updateClipList();
      }
    });
    
    clipList.appendChild(item);
  });
}

function deleteSingleClip(index) {
  saveState();
  clips.splice(index, 1);
  checkedClips.delete(index);
  
  const newChecked = new Set();
  checkedClips.forEach(i => {
    if (i > index) newChecked.add(i - 1);
    else if (i < index) newChecked.add(i);
  });
  checkedClips = newChecked;
  
  if (selectedClipIndex === index) selectedClipIndex = -1;
  else if (selectedClipIndex > index) selectedClipIndex--;
  
  renderClips();
  updateClipList();
  addMessage('クリップ ' + (index + 1) + ' を削除しました', 'success');
}

function playClip(index) {
  if (!videoElement || !clips[index]) return;
  
  videoElement.currentTime = clips[index].start;
  videoElement.play();
  
  const checkTime = setInterval(() => {
    if (videoElement.currentTime >= clips[index].end) {
      videoElement.pause();
      clearInterval(checkTime);
    }
  }, 100);
  
  addMessage('クリップ ' + (index + 1) + ' を再生中', 'info');
}

function handleAddClip() {
  if (!currentAudioBuffer) {
    addMessage('先に動画ファイルを読み込んでください', 'error');
    return;
  }
  
  saveState();
  
  const duration = currentAudioBuffer.duration;
  const defaultDuration = parseFloat(document.getElementById('clipDuration').value) || 10;
  const newStart = videoElement.currentTime || 0;
  const newEnd = Math.min(newStart + defaultDuration, duration);
  
  clips.push({ start: newStart, end: newEnd });
  selectedClipIndex = clips.length - 1;
  
  renderClips();
  updateClipList();
  addMessage(formatTime(newStart) + ' にクリップを追加しました', 'success');
  
  document.getElementById('downloadSegmentsBtn').style.display = 'inline-block';
  document.getElementById('clipEditSection').style.display = 'block';
}

function handleDeleteClip() {
  if (checkedClips.size === 0) {
    addMessage('削除するクリップにチェックを入れてください', 'error');
    return;
  }
  
  saveState();
  
  const toDelete = Array.from(checkedClips).sort((a, b) => b - a);
  toDelete.forEach(index => clips.splice(index, 1));
  
  checkedClips.clear();
  selectedClipIndex = -1;
  
  renderClips();
  updateClipList();
  addMessage(toDelete.length + '個のクリップを削除しました', 'success');
}

function handleCanvasClick(e) {
  if (!currentAudioBuffer || !videoElement) return;
  
  const rect = canvasElement.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const percent = x / rect.width;
  const viewDuration = currentAudioBuffer.duration / zoomLevel;
  const time = scrollOffset + (percent * viewDuration);
  
  videoElement.currentTime = time;
  addMessage('再生位置: ' + formatTime(time), 'info');
}

async function handleDownloadSegments() {
  if (!clips || clips.length === 0 || !currentFile) {
    addMessage('切り出すクリップがありません', 'error');
    return;
  }
  
  const btn = document.getElementById('downloadSegmentsBtn');
  const originalText = btn.innerHTML;
  btn.innerHTML = '処理中<span class="spinner"></span>';
  btn.disabled = true;
  
  isProcessing = true;
  videoElement.pause();
  videoElement.muted = true;
  
  addMessage('動画クリップを作成しています...', 'info');
  
  try {
    await createSegmentedVideos(currentFile, clips);
    addMessage('すべてのクリップの作成が完了しました', 'success');
  } catch (e) {
    addMessage('エラー: ' + e.message, 'error');
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
    isProcessing = false;
    videoElement.muted = false;
  }
}

async function createSegmentedVideos(file, clips) {
  for (let i = 0; i < clips.length; i++) {
    const clip = clips[i];
    updateProgress('クリップ ' + (i+1) + '/' + clips.length + ' を作成中...', (i / clips.length) * 100);
    
    await createSegmentVideo(file, clip.start, clip.end, i + 1);
    addMessage('クリップ ' + (i+1) + ' を保存しました(' + formatTime(clip.start) + ' - ' + formatTime(clip.end) + ')', 'success');
  }
  
  updateProgress('完了', 100);
}

async function createSegmentVideo(file, startTime, endTime, segmentNumber) {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video');
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    
    const chunks = [];
    let mediaRecorder;
    let audioDestination;
    let audioCtx;
    
    video.src = URL.createObjectURL(file);
    video.muted = false;
    
    video.addEventListener('loadedmetadata', () => {
      const resolution = document.getElementById('resolutionSelect').value;
      const format = document.getElementById('formatSelect').value;
      const codec = document.getElementById('codecSelect').value;
      const audioCodec = document.getElementById('audioCodecSelect').value;
      
      let targetWidth = video.videoWidth;
      let targetHeight = video.videoHeight;
      
      if (resolution !== 'original') {
        const targetHeightNum = parseInt(resolution);
        const aspectRatio = video.videoWidth / video.videoHeight;
        targetHeight = targetHeightNum;
        targetWidth = Math.round(targetHeight * aspectRatio);
      }
      
      canvas.width = targetWidth - (targetWidth % 2);
      canvas.height = targetHeight - (targetHeight % 2);
      
      const stream = canvas.captureStream(30);
      
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const source = audioCtx.createMediaElementSource(video);
        audioDestination = audioCtx.createMediaStreamDestination();
        source.connect(audioDestination);
        
        if (audioDestination.stream.getAudioTracks().length > 0 && format !== 'mp3') {
          stream.addTrack(audioDestination.stream.getAudioTracks()[0]);
        }
      } catch (e) {
        addMessage('音声処理で警告: ' + e.message, 'warning');
      }
      
      let mimeType = '';
      let extension = format;
      
      if (format === 'mp3') {
        if (audioDestination && audioDestination.stream.getAudioTracks().length > 0) {
          const audioOnlyStream = new MediaStream([audioDestination.stream.getAudioTracks()[0]]);
          mimeType = 'audio/webm'; 
          extension = 'mp3'; 
          try {
              mediaRecorder = new MediaRecorder(audioOnlyStream, { mimeType: mimeType });
          } catch(e) { reject(new Error('音声のみの録音開始に失敗しました')); return; }
        } else {
          reject(new Error('音声トラックが見つかりません'));
          return;
        }
      } else {
        if ((format === 'mp4' || format === 'mov') && codec === 'h264' && audioCodec === 'aac') {
            const mp4MimeType = 'video/mp4; codecs="avc1.42E01E, mp4a.40.2"';
            if (MediaRecorder.isTypeSupported(mp4MimeType)) {
                mimeType = mp4MimeType;
            }
        }

        if (!mimeType) {
            const genericMimeType = `video/${format === 'mp4' ? 'webm' : format}; codecs=${codec},${audioCodec}`;
            if (MediaRecorder.isTypeSupported(genericMimeType)) {
                mimeType = genericMimeType;
                if(format === 'mp4') {
                    addMessage('H.264/AACでのMP4出力がサポートされていないため、WebM形式で出力します。', 'warning');
                    extension = 'webm';
                }
            } else {
                addMessage(`指定の組み合わせ「${format}/${codec}/${audioCodec}」はサポートされていません。WebM/VP9/Opusで出力します。`, 'warning');
                mimeType = 'video/webm; codecs=vp9,opus';
                extension = 'webm';
            }
        }
      }
      
      try {
        if (!mediaRecorder) { 
            mediaRecorder = new MediaRecorder(stream, {
                mimeType: mimeType,
                videoBitsPerSecond: 2500000,
                audioBitsPerSecond: 128000,
            });
        }
      } catch (e) {
        addMessage(`録画の初期化に失敗しました: ${e.message}`, 'error');
        reject(e);
        return;
      }
      
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      
      mediaRecorder.onstop = () => {
        const finalMimeType = mediaRecorder.mimeType || 'video/mp4';
        const blob = new Blob(chunks, { type: finalMimeType });
        const baseName = file.name.replace(/\.[^/.]+$/, '');
        const resLabel = resolution === 'original' ? 'original' : resolution + 'p';
        const filename = `${baseName}_${resLabel}_clip_${segmentNumber}.${extension}`;
        
        downloadFile(blob, filename);
        
        URL.revokeObjectURL(video.src);
        if (audioCtx) audioCtx.close();
        resolve();
      };
      
      mediaRecorder.onerror = (e) => {
        addMessage('録画エラー: ' + e.error, 'error');
        reject(e.error);
      };
      
      video.currentTime = startTime;
    });
    
    video.addEventListener('seeked', () => {
      if (!mediaRecorder) {
          reject(new Error("MediaRecorderが利用できません。"));
          return;
      }
      mediaRecorder.start();
      video.play();
      
      const draw = () => {
        if (video.currentTime >= endTime || video.paused) {
          if (mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
          }
          return;
        }
        if (document.getElementById('formatSelect').value !== 'mp3') {
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        }
        requestAnimationFrame(draw);
      };
      
      draw();
    });
    
    video.addEventListener('error', (e) => {
      addMessage('動画読み込みエラー', 'error');
      reject(e);
    });
  });
}

function downloadFile(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(1);
  return mins + ':' + secs.padStart(4, '0');
}

function formatTimeForPopup(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
}

function updateProgress(text, percent) {
  document.getElementById('progressText').textContent = text;
  document.getElementById('progressPercent').textContent = Math.round(percent) + '%';
  document.getElementById('progressFill').style.width = percent + '%';
}

function addMessage(text, type) {
  const message = document.createElement('div');
  message.className = 'message message-' + type;
  const time = new Date().toLocaleTimeString();
  message.textContent = '[' + time + '] ' + text;
  const messageArea = document.getElementById('messageArea');
  messageArea.appendChild(message);
  messageArea.scrollTop = messageArea.scrollHeight;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}