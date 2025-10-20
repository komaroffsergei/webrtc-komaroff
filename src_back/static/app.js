(function(){
  const cfg = window.AppConfig;

  // UI bindings helper exposed for VAD threshold access
  const els = {
    status: document.getElementById('status'),
    connect: document.getElementById('connect'),
    stop: document.getElementById('stop'),
    vadEnable: document.getElementById('vadEnable'),
    vadThresh: document.getElementById('vadThresh'),
    vadLevel: document.getElementById('vadLevel'),
    ecEnable: document.getElementById('ecEnable'),
    nsEnable: document.getElementById('nsEnable'),
    remoteAudio: document.getElementById('remoteAudio'),
    waveIn: document.getElementById('waveIn').getContext('2d'),
    waveOut: document.getElementById('waveOut').getContext('2d'),
    log: document.getElementById('log'),
    logClear: document.getElementById('logClear'),
    logAutoscroll: document.getElementById('logAutoscroll'),
  };

  if (window.AppLog){ AppLog.init({ el: els.log, clearBtn: els.logClear, autoChk: els.logAutoscroll, maxLines: 5000 }); }

  window.UIBindings = {
    vadThreshold: () => els.vadThresh.valueAsNumber,
  };

  els.vadLevel.textContent = `${Math.round(els.vadThresh.valueAsNumber)} dBFS`;
  els.vadThresh.addEventListener('input', () => {
    els.vadLevel.textContent = `${Math.round(els.vadThresh.valueAsNumber)} dBFS`;
  });

  let pc = null;
  let sender = null;
  let micStream = null;
  let micTrack = null;
  let vadInstance = null;
  // Pre-warm RTCPeerConnection to utilize ICE candidate pool
  window.addEventListener('load', async ()=>{
    try{
      if (!pc) {
        pc = await window.WebRTC.createPeer(cfg);
        if (window.AppLog) AppLog.emit('[pc] prewarmed');
      }
    }catch(e){ console.warn('prewarm pc failed', e); }
  });

  function getUserMediaOpts(){
    return {
      audio: {
        echoCancellation: els.ecEnable.checked,
        noiseSuppression: els.nsEnable.checked,
        autoGainControl: false,
        channelCount: 1,
        sampleRate: 48000,
        sampleSize: 16
      },
      video: false
    };
  }

  function stopMic(){
    try { if (micStream) micStream.getTracks().forEach(t => t.stop()); } catch{}
  }
  function stopVAD(){
    try { vadInstance && vadInstance.cleanup(); } catch{}
    vadInstance = null;
  }

  async function reconfigureMic(){
    try{
      const s = await navigator.mediaDevices.getUserMedia(getUserMediaOpts());
      const newTrack = s.getAudioTracks()[0];
      const sdr = pc?.getSenders().find(x => x.track && x.track.kind === 'audio');
      if (sdr && newTrack){
        await sdr.replaceTrack(newTrack);
        sender = sdr;
      }
      stopMic();
      micStream = s;
      micTrack = newTrack;
      els.status.textContent = `mic reconfigured: EC=${els.ecEnable.checked} NS=${els.nsEnable.checked}`;
      if (window.AppLog) AppLog.emit('[media] mic reconfigured', { echoCancellation: els.ecEnable.checked, noiseSuppression: els.nsEnable.checked });
      if (els.vadEnable.checked){
        await applyVAD();
      }
    }catch(e){ console.warn('failed to reconfigure mic', e); }
  }

  async function applyVAD(){
    if (!micTrack || !sender) return;
    stopVAD();
    vadInstance = window.VAD.createEnergyVAD(micTrack, cfg, (gate)=>{
      els.vadLevel.textContent = `${gate} dBFS`;
      if (window.AppLog) AppLog.emit('[vad] level', gate);
    });
    await sender.replaceTrack(vadInstance.track);
  }

  function setupInputViz(){
    try{
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const drawer = window.AudioViz.createWaveDrawer(els.waveIn, cfg);
      window.AudioViz.attachAnalyserDraw(ac, micStream, cfg, (hist)=>drawer(hist, cfg.ui.colors.in));
    }catch(e){ console.warn('waveIn failed', e); }
  }

  function setupOutputViz(outStream){
    try{
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const drawer = window.AudioViz.createWaveDrawer(els.waveOut, cfg);
      window.AudioViz.attachAnalyserDraw(ac, outStream, cfg, (hist)=>drawer(hist, cfg.ui.colors.out));
    }catch(e){ console.warn('waveOut failed', e); }
  }

  async function onConnect(){
    try{
      micStream = await navigator.mediaDevices.getUserMedia(getUserMediaOpts());
      micTrack = micStream.getAudioTracks()[0];
      setupInputViz();

      pc = await window.WebRTC.createPeer(cfg);

      // add track, optionally VAD-wrapped later
      sender = pc.addTrack(micTrack, micStream);

      // OPUS encoder tuning: bitrate + DTX
      try{
        const params = sender.getParameters() || {};
        params.encodings = params.encodings || [{}];
        params.encodings[0].maxBitrate = cfg.audio.opus.maxBitrate;
        params.encodings[0].dtx = true;
        await sender.setParameters(params);
      }catch(e){ console.warn('failed to set sender params', e); }

      // Prefer OPUS codec explicitly where supported
      try{
        const txv = pc.getTransceivers().find(t => t.sender && t.sender.track === micTrack) || pc.getTransceivers().find(t => t.sender && t.sender.track && t.sender.track.kind === 'audio');
        if (txv && typeof RTCRtpSender !== 'undefined' && RTCRtpSender.getCapabilities){
          const caps = RTCRtpSender.getCapabilities('audio');
          if (caps && caps.codecs && txv.setCodecPreferences){
            const opus = caps.codecs.filter(c => /opus/i.test(c.mimeType));
            const cn = caps.codecs.filter(c => /CN/i.test(c.mimeType));
            if (opus.length){ txv.setCodecPreferences([...opus, ...cn]); }
          }
        }
      }catch(e){ console.warn('failed to set codec preferences', e); }

      pc.ontrack = (event) => {
        const stream = event.streams?.[0] || new MediaStream([event.track]);
        els.remoteAudio.srcObject = stream;
        els.remoteAudio.muted = false;
        els.remoteAudio.play().catch(err => console.warn('[audio] play() rejected', err));
        setupOutputViz(stream);
      };

      if (els.vadEnable.checked){ await applyVAD(); }

      els.status.textContent = 'connecting...';
      await window.WebRTC.negotiate(pc, cfg);

      els.connect.disabled = true;
      els.stop.disabled = false;
      els.status.textContent = 'connected';
    }catch(e){
      console.error(e);
      els.status.textContent = 'error: ' + e.message;
    }
  }

  function onStop(){
    try{ stopVAD(); }catch{}
    if (pc){
      try{ pc.getSenders().forEach(s=>{ try{ if (s.track) s.replaceTrack(null); }catch{} }); }catch{}
      try{ pc.getSenders().forEach(s=>{ try{ if (s.track) s.track.stop(); }catch{} }); }catch{}
      try{ pc.close(); }catch{}
    }
    pc = null;
    stopMic();
    els.connect.disabled = false;
    els.stop.disabled = true;
    els.status.textContent = 'stopped';
    els.remoteAudio.srcObject = null;
  }

  // UI events
  els.connect.onclick = onConnect;
  els.stop.onclick = onStop;
  els.ecEnable.onchange = reconfigureMic;
  els.nsEnable.onchange = reconfigureMic;
  els.vadEnable.onchange = async ()=>{
    if (!sender) return;
    if (els.vadEnable.checked) await applyVAD(); else { stopVAD(); await sender.replaceTrack(micTrack); }
  };
})();
