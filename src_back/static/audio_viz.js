// Simple time-domain waveform visualizer for MediaStreamAudioSourceNode
(function(){
  function createWaveDrawer(ctx2d, config){
    const W = config.ui.canvas.width;
    const H = config.ui.canvas.height;
    const mid = H/2;
    const amp = mid*1.8;
    const gridColor = config.ui.colors.grid;
    return function draw(history, stroke){
      ctx2d.clearRect(0,0,W,H);
      ctx2d.strokeStyle = gridColor; ctx2d.lineWidth = 1;
      ctx2d.beginPath(); ctx2d.moveTo(0,mid); ctx2d.lineTo(W,mid); ctx2d.stroke();
      const step = Math.max(1, Math.floor(history.length / W));
      ctx2d.strokeStyle = stroke; ctx2d.lineWidth = 2;
      ctx2d.beginPath();
      for (let x=0, i=0; x<W; x++, i+=step) {
        let lo=1, hi=-1;
        const end = Math.min(i+step, history.length);
        for (let j=i; j<end; j++) { const v = history[j]; if (v<lo) lo=v; if (v>hi) hi=v; }
        const y1 = mid + lo*amp, y2 = mid + hi*amp;
        ctx2d.moveTo(x, y1); ctx2d.lineTo(x, y2);
      }
      ctx2d.stroke();
    }
  }

  function attachAnalyserDraw(ac, stream, config, onDraw){
    const an = ac.createAnalyser();
    an.fftSize = config.audio.analyser.fftSize;
    const src = ac.createMediaStreamSource(stream);
    src.connect(an);
    const chunk = new Float32Array(an.fftSize);
    const maxLen = Math.max(1, Math.floor(ac.sampleRate * config.audio.analyser.historySeconds));
    let history = new Float32Array(0);
    function step(){
      an.getFloatTimeDomainData(chunk);
      const combined = new Float32Array(Math.min(history.length + chunk.length, maxLen));
      const overflow = Math.max(0, history.length + chunk.length - maxLen);
      if (overflow > 0 && history.length > overflow) {
        combined.set(history.subarray(overflow));
        combined.set(chunk, history.length - overflow);
      } else {
        combined.set(history);
        combined.set(chunk, history.length);
      }
      history = combined;
      onDraw(history);
      requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
    return { stop(){ try{ src.disconnect(); }catch{} } };
  }

  window.AudioViz = { createWaveDrawer, attachAnalyserDraw };
})();
