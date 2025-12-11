import type { AppConfig } from "../config/appConfig";

export type VADInstance = {
  track: MediaStreamTrack;
  cleanup: () => void;
};

export function createEnergyVAD(
  sourceTrack: MediaStreamTrack,
  config: AppConfig,
  getThreshold: () => number,
  onThresholdText?: (value: number) => void,
): VADInstance {
  const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
  const src = ctx.createMediaStreamSource(new MediaStream([sourceTrack]));
  const analyser = ctx.createAnalyser();
  analyser.fftSize = config.audio.vad.fftSize;

  const gainNode = ctx.createGain();
  gainNode.gain.value = 1.0;

  src.connect(analyser);
  analyser.connect(gainNode);

  const dest = ctx.createMediaStreamDestination();
  gainNode.connect(dest);

  const data = new Float32Array(analyser.fftSize);
  let stopped = false;

  const update = () => {
    if (stopped) return;

    analyser.getFloatTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) {
      sum += data[i] * data[i];
    }
    const rms = Math.sqrt(sum / data.length);
    const db = 20 * Math.log10(rms + 1e-12);
    const gate = getThreshold();
    onThresholdText?.(Math.round(gate));

    const active = db > gate;
    const target = active ? 1.0 : 0.0;
    const T = active ? config.audio.vad.attackSeconds : config.audio.vad.releaseSeconds;
    if (gainNode.gain.value !== target) {
      gainNode.gain.setTargetAtTime(target, ctx.currentTime, T);
    }

    requestAnimationFrame(update);
  };

  requestAnimationFrame(update);

  const outputTrack = dest.stream.getAudioTracks()[0];

  const cleanup = () => {
    stopped = true;
    try {
      src.disconnect();
    } catch {
      /* ignore */
    }
    try {
      analyser.disconnect();
    } catch {
      /* ignore */
    }
    try {
      gainNode.disconnect();
    } catch {
      /* ignore */
    }
    ctx.close().catch(() => undefined);
  };

  return { track: outputTrack, cleanup };
}
