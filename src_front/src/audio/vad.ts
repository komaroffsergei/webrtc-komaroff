import type { AppConfig } from "../config/appConfig";

export type VadInstance = { track: MediaStreamTrack; stop: () => void };

export function createEnergyVad(
  sourceTrack: MediaStreamTrack,
  config: AppConfig,
  getThresholdDb: () => number,
  onThresholdText?: (value: number) => void,
  onSpeechActivityChange?: (active: boolean) => void,
): VadInstance {
  const ctx = new AudioContext();
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
  let lastActive: boolean | null = null;

  const tick = () => {
    if (stopped) return;

    analyser.getFloatTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i];

    const rms = Math.sqrt(sum / data.length);
    const db = 20 * Math.log10(rms + 1e-12);

    const gate = getThresholdDb();
    onThresholdText?.(Math.round(gate));

    const active = db > gate;
    if (lastActive === null) {
      lastActive = active;
      if (active) {
        onSpeechActivityChange?.(true);
      }
    } else if (lastActive !== active) {
      lastActive = active;
      onSpeechActivityChange?.(active);
    }

    const target = active ? 1.0 : 0.0;
    const T = active ? config.audio.vad.attackSeconds : config.audio.vad.releaseSeconds;

    if (gainNode.gain.value !== target) {
      gainNode.gain.setTargetAtTime(target, ctx.currentTime, T);
    }

    requestAnimationFrame(tick);
  };

  requestAnimationFrame(tick);

  const outputTrack = dest.stream.getAudioTracks()[0];

  return {
    track: outputTrack,
    stop: () => {
      stopped = true;
      src.disconnect();
      analyser.disconnect();
      gainNode.disconnect();
      void ctx.close();
    },
  };
}
