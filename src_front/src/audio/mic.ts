import type { AudioState } from "./audioState";

export async function startMic(state: AudioState): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: state.echoCancellation,
      noiseSuppression: state.noiseSuppression,
    },
    video: false,
  });
}

export function stopMic(stream: MediaStream | null): void {
  stream?.getTracks().forEach((t) => t.stop());
}
