import type { AppConfig } from "../config/appConfig";
import type { AssistantElements } from "./elements";

type Stopper = () => void;

function drawWave(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  history: Float32Array,
  strokeStyle: string,
): void {
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = strokeStyle;
  ctx.lineWidth = 2;
  ctx.beginPath();

  const mid = height / 2;
  const amp = mid * 0.9;
  const step = Math.max(1, Math.floor(history.length / width));

  for (let x = 0, i = 0; x < width; x += 1, i += step) {
    let lo = 1;
    let hi = -1;
    const end = Math.min(i + step, history.length);
    for (let j = i; j < end; j += 1) {
      const v = history[j];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    ctx.moveTo(x, mid + lo * amp);
    ctx.lineTo(x, mid + hi * amp);
  }

  ctx.stroke();
}

function startAnalyserLoop(
  audioContext: AudioContext,
  stream: MediaStream,
  fftSize: number,
  historySeconds: number,
  onDraw: (history: Float32Array) => void,
): Stopper {
  const analyser = audioContext.createAnalyser();
  analyser.fftSize = fftSize;

  const source = audioContext.createMediaStreamSource(stream);
  source.connect(analyser);

  const chunk = new Float32Array(analyser.fftSize);
  const maxLen = Math.max(1, Math.floor(audioContext.sampleRate * historySeconds));

  let history = new Float32Array(0);
  let stopped = false;

  const tick = () => {
    if (stopped) return;

    analyser.getFloatTimeDomainData(chunk);

    const total = Math.min(history.length + chunk.length, maxLen);
    const next = new Float32Array(total);

    const overflow = Math.max(0, history.length + chunk.length - maxLen);
    if (overflow > 0 && history.length > overflow) {
      next.set(history.subarray(overflow));
      next.set(chunk, history.length - overflow);
    } else {
      next.set(history);
      next.set(chunk, history.length);
    }

    history = next;
    onDraw(history);
    requestAnimationFrame(tick);
  };

  requestAnimationFrame(tick);

  return () => {
    stopped = true;
    source.disconnect();
  };
}

export function resizeWaveCanvases(el: AssistantElements): void {
  if (el.waveBackground && el.chatWindow) {
    const rect = el.chatWindow.getBoundingClientRect();
    el.waveBackground.width = rect.width + 20;
    el.waveBackground.height = rect.height + 20;
  }
  if (el.micWaveform) {
    el.micWaveform.width = 140;
    el.micWaveform.height = 40;
  }
}

export function startWaveforms(
  el: AssistantElements,
  config: AppConfig,
  stream: MediaStream,
): { stop: Stopper } {
  resizeWaveCanvases(el);

  const stoppers: Stopper[] = [];
  const ctxBg = el.waveBackground?.getContext("2d") ?? null;
  const ctxMic = el.micWaveform?.getContext("2d") ?? null;

  if (ctxBg && el.waveBackground) {
    const ac = new AudioContext();
    stoppers.push(
      startAnalyserLoop(
        ac,
        stream,
        config.audio.analyser.fftSizeBg,
        config.audio.analyser.historySecondsBg,
        (h) => drawWave(ctxBg, el.waveBackground!.width, el.waveBackground!.height, h, "#007aff"),
      ),
    );
    stoppers.push(() => void ac.close());
  }

  if (ctxMic && el.micWaveform) {
    const ac = new AudioContext();
    stoppers.push(
      startAnalyserLoop(
        ac,
        stream,
        config.audio.analyser.fftSizeMic,
        config.audio.analyser.historySecondsMic,
        (h) => drawWave(ctxMic, el.micWaveform!.width, el.micWaveform!.height, h, "#fff"),
      ),
    );
    stoppers.push(() => void ac.close());
  }

  return {
    stop: () => stoppers.forEach((s) => s()),
  };
}
