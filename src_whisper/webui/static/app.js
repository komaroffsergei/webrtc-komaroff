(() => {
  const statusEl = document.getElementById('status');
  const repliesEl = document.getElementById('replies');
  const startBtn = document.getElementById('start');
  const stopBtn = document.getElementById('stop');
  const downloadEl = document.getElementById('download');

  function basePath() {
    const meta = document.querySelector('meta[name="webui-base-path"]');
    return meta ? (meta.getAttribute('content') || '') : '';
  }

  function wsUrl() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return proto + '//' + window.location.host + basePath() + '/ws';
  }

  function setStatus(text, cls='') {
    statusEl.className = cls;
    statusEl.textContent = text;
  }

  function appendReply(obj) {
    const line = JSON.stringify(obj);
    repliesEl.textContent = (repliesEl.textContent ? repliesEl.textContent + '\n' : '') + line;
  }

  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  function resampleLinear(input, inRate, outRate) {
    if (inRate === outRate) return input;
    const ratio = outRate / inRate;
    const outLen = Math.max(1, Math.floor(input.length * ratio));
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const t = i / ratio;
      const idx = Math.floor(t);
      const frac = t - idx;
      const s0 = input[idx] || 0;
      const s1 = input[idx + 1] || s0;
      out[i] = s0 + (s1 - s0) * frac;
    }
    return out;
  }

  async function decodeToMonoFloat32(file) {
    const buf = await file.arrayBuffer();
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const audioBuf = await ac.decodeAudioData(buf.slice(0));
    const ch = audioBuf.numberOfChannels;
    const len = audioBuf.length;
    let mono = new Float32Array(len);
    for (let c = 0; c < ch; c++) {
      const data = audioBuf.getChannelData(c);
      for (let i = 0; i < len; i++) mono[i] += data[i];
    }
    for (let i = 0; i < len; i++) mono[i] /= Math.max(1, ch);
    return { samples: mono, sampleRate: audioBuf.sampleRate };
  }

  function float32ToPcm16le(samples, offset, frameSamples) {
    const buf = new ArrayBuffer(frameSamples * 2);
    const view = new DataView(buf);
    for (let i = 0; i < frameSamples; i++) {
      const v = samples[offset + i] || 0;
      const clamped = Math.max(-1, Math.min(1, v));
      const s = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);
      view.setInt16(i * 2, s, true);
    }
    return buf;
  }

  // Splits decoded audio into fixed-size PCM16LE frames.
  async function* wavToPcmFrames(file, targetRate, frameMs) {
    const decoded = await decodeToMonoFloat32(file);
    const resampled = resampleLinear(decoded.samples, decoded.sampleRate, targetRate);
    const frameSamples = Math.round(targetRate * frameMs / 1000);
    const totalFrames = Math.ceil(resampled.length / frameSamples);
    for (let i = 0; i < totalFrames; i++) {
      const off = i * frameSamples;
      yield { index: i, total: totalFrames, frame: float32ToPcm16le(resampled, off, frameSamples) };
    }
  }

  let ws = null;
  let stopped = false;
  let currentRunId = '';

  stopBtn.addEventListener('click', () => {
    stopped = true;
    try { ws && ws.send(JSON.stringify({ type: 'stop' })); } catch (_) {}
    try { ws && ws.close(); } catch (_) {}
  });

  startBtn.addEventListener('click', async () => {
    const file = document.getElementById('wav').files[0];
    if (!file) { setStatus('Select a WAV file first', 'err'); return; }

    const natsUrl = document.getElementById('natsUrl').value.trim();
    const inSubject = document.getElementById('inSubject').value.trim();
    const outSubject = document.getElementById('outSubject').value.trim();
    const sessionId = document.getElementById('sessionId').value.trim();
    const sampleRate = parseInt(document.getElementById('sampleRate').value, 10);
    const frameMs = parseInt(document.getElementById('frameMs').value, 10);
    const timeoutS = parseFloat(document.getElementById('timeoutS').value);
    const uiUpdateEveryMs = 400;
    let lastUiUpdateAt = 0;

    repliesEl.textContent = '';
    downloadEl.textContent = '';
    currentRunId = '';
    stopped = false;
    startBtn.disabled = true;
    stopBtn.disabled = false;

    setStatus('Connecting WebSocket...', '');
    ws = new WebSocket(wsUrl());
    ws.binaryType = 'arraybuffer';

    ws.onmessage = (ev) => {
      if (typeof ev.data !== 'string') return;
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }

      if (msg.type === 'reply') appendReply(msg.data);

      if (msg.type === 'stats') {
        if (msg.run_id) currentRunId = msg.run_id;
        setStatus(JSON.stringify(msg, null, 2), 'ok');
      }

      if (msg.type === 'done') {
        if (msg.run_id) currentRunId = msg.run_id;
        setStatus(JSON.stringify(msg, null, 2), 'ok');
        if (currentRunId) {
          const a = document.createElement('a');
          a.href = basePath() + '/runs/' + encodeURIComponent(currentRunId);
          a.textContent = 'Download JSONL';
          downloadEl.innerHTML = '';
          downloadEl.appendChild(a);
        }
      }

      if (msg.type === 'error') setStatus(JSON.stringify(msg, null, 2), 'err');
    };

    ws.onclose = () => {
      startBtn.disabled = false;
      stopBtn.disabled = true;
    };

    ws.onerror = () => setStatus('WebSocket error', 'err');

    await new Promise((resolve) => ws.onopen = resolve);
    ws.send(JSON.stringify({
      type: 'start',
      nats_url: natsUrl,
      in_subject: inSubject,
      out_subject: outSubject,
      session_id: sessionId,
      sample_rate: sampleRate,
      frame_ms: frameMs,
      timeout_s: timeoutS,
      file_name: file.name,
    }));

    setStatus('Decoding and sending frames...', '');
    try {
      for await (const item of wavToPcmFrames(file, sampleRate, frameMs)) {
        if (stopped) break;
        ws.send(item.frame);
        const now = Date.now();
        if ((now - lastUiUpdateAt) >= uiUpdateEveryMs) {
          lastUiUpdateAt = now;
          setStatus(JSON.stringify({ type: 'sending', frames_sent: item.index, total_frames: item.total }, null, 2));
          while (ws.bufferedAmount > 4 * 1024 * 1024) await sleep(20);
          await sleep(0);
        }
      }
    } catch (e) {
      setStatus('Failed to process WAV: ' + (e && e.message ? e.message : String(e)), 'err');
      try { ws.close(); } catch (_) {}
      return;
    }

    if (!stopped) ws.send(JSON.stringify({ type: 'end' }));
  });
})();
