import type { AppConfig } from "../config/appConfig";
import type { AssistantElements } from "../ui/elements";
import type { AudioState } from "../audio/audioState";
import { startMic, stopMic } from "../audio/mic";
import { createPeer } from "./peer";
import { negotiate } from "./negotiate";
import { createEnergyVad, type VadInstance } from "../audio/vad";
import { resizeWaveCanvases, startWaveforms } from "../ui/waves";

type Session = {
  peer: RTCPeerConnection;
  sender: RTCRtpSender;
  micStream: MediaStream;
  vad: VadInstance | null;
  wavesStop: (() => void) | null;
};

let session: Session | null = null;

export async function connectSession(
  config: AppConfig,
  el: AssistantElements,
  audio: AudioState,
  onVadText: (t: string) => void,
): Promise<void> {
  if (session) return;

  const micStream = await startMic(audio);
  const peer = createPeer(config);

  peer.ontrack = (e) => {
    if (el.remoteAudio) el.remoteAudio.srcObject = e.streams[0];
  };

  const track = micStream.getAudioTracks()[0];
  const sender = peer.addTrack(track, micStream);

  let vad: VadInstance | null = null;
  if (audio.vadEnabled) {
    vad = createEnergyVad(track, config, () => audio.vadThreshold, (v) => onVadText(`${v} dBFS`));
    await sender.replaceTrack(vad.track);
  }

  resizeWaveCanvases(el);
  const waves = startWaveforms(el, config, micStream);

  await negotiate(peer, config);

  session = { peer, sender, micStream, vad, wavesStop: waves.stop };
}

export function disconnectSession(): void {
  if (!session) return;

  session.vad?.stop();
  session.wavesStop?.();

  stopMic(session.micStream);
  session.peer.close();

  session = null;
}

export function isConnected(): boolean {
  return !!session;
}
