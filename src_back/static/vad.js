// Energy-based VAD with gating using WebAudio
(function(){
  function createEnergyVAD(sourceTrack, config, onLevelText){
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(new MediaStream([sourceTrack]));
    const analyser = ctx.createAnalyser();
    analyser.fftSize = config.audio.vad.fftSize;
    const gainNode = ctx.createGain();
    gainNode.gain.value = 1.0;
    src.connect(analyser);
    analyser.connect(gainNode);
    const dest = ctx.createMediaStreamDestination();
    gainNode.connect(dest);

    const data = new Float32Array(analyser.frequencyBinCount);
    let stopped = false;

    function tick(){
      analyser.getFloatTimeDomainData(data);
      let sum = 0; for (let i=0;i<data.length;i++) sum += data[i]*data[i];
      const rms = Math.sqrt(sum / data.length);
      const db = 20 * Math.log10(rms + 1e-12);
      const gate = window.UIBindings?.vadThreshold?.() ?? -55;
      onLevelText && onLevelText(Math.round(gate));
      const active = db > gate;
      const target = active ? 1.0 : 0.0;
      const T = active ? config.audio.vad.attackSeconds : config.audio.vad.releaseSeconds;
      if (gainNode.gain.value !== target) gainNode.gain.setTargetAtTime(target, ctx.currentTime, T);
      if (!stopped) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);

    const out = dest.stream.getAudioTracks()[0];

    function cleanup(){
      try{ stopped = true; }catch{}
      try{ src.disconnect(); }catch{}
      try{ analyser.disconnect(); }catch{}
      try{ gainNode.disconnect(); }catch{}
      try{ ctx.close(); }catch{}
    }

    return { track: out, cleanup };
  }

  window.VAD = { createEnergyVAD };
})();
