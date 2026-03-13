export type VadInstance = { stop: () => void };

export function createEnergyVad(
  sourceTrack: MediaStreamTrack,
  onThresholdText?: (value: number) => void,
): VadInstance {
  const ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(new MediaStream([sourceTrack]));
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  src.connect(analyser);

  const data = new Float32Array(analyser.fftSize);
  let stopped = false;

  const tick = () => {
    if (stopped) return;

    analyser.getFloatTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i += 1) sum += data[i] * data[i];

    const rms = Math.sqrt(sum / data.length);
    const db = 20 * Math.log10(rms + 1e-12);

    onThresholdText?.(Math.round(db));

    requestAnimationFrame(tick);
  };

  requestAnimationFrame(tick);

  return {
    stop: () => {
      stopped = true;
      src.disconnect();
      analyser.disconnect();
      void ctx.close();
    },
  };
}
