export type CanvasConfig = {
  width: number;
  height: number;
  gridColor: string;
};

export type AnalyserConfig = {
  fftSize: number;
  historySeconds: number;
};

export type WaveDrawer = (history: Float32Array, stroke: string) => void;

export function createWaveDrawer(
  ctx: CanvasRenderingContext2D,
  canvas: CanvasConfig,
): WaveDrawer {
  const width = canvas.width;
  const height = canvas.height;
  const mid = height / 2;
  const amp = mid * 1.8;

  return (history, stroke) => {
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = canvas.gridColor;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(width, mid);
    ctx.stroke();

    const step = Math.max(1, Math.floor(history.length / width));
    ctx.strokeStyle = stroke;
    ctx.lineWidth = 2;
    ctx.beginPath();
    for (let x = 0, i = 0; x < width; x += 1, i += step) {
      let lo = 1;
      let hi = -1;
      const end = Math.min(i + step, history.length);
      for (let j = i; j < end; j += 1) {
        const value = history[j];
        if (value < lo) lo = value;
        if (value > hi) hi = value;
      }
      const y1 = mid + lo * amp;
      const y2 = mid + hi * amp;
      ctx.moveTo(x, y1);
      ctx.lineTo(x, y2);
    }
    ctx.stroke();
  };
}

export function attachAnalyserDraw(
  audioContext: AudioContext,
  stream: MediaStream,
  analyserConfig: AnalyserConfig,
  onDraw: (history: Float32Array) => void,
): { stop: () => void } {
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = analyserConfig.fftSize;
  const source = audioContext.createMediaStreamSource(stream);
  source.connect(analyser);

  const chunk = new Float32Array(analyser.fftSize);
  const maxLen = Math.max(
    1,
    Math.floor(audioContext.sampleRate * analyserConfig.historySeconds),
  );
  let history = new Float32Array(0);
  let stopped = false;

  const step = () => {
    if (stopped) return;

    analyser.getFloatTimeDomainData(chunk);
    const combined = new Float32Array(
      Math.min(history.length + chunk.length, maxLen),
    );
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
  };

  requestAnimationFrame(step);

  return {
    stop: () => {
      stopped = true;
      try {
        source.disconnect();
      } catch {
        /* ignore */
      }
    },
  };
}
