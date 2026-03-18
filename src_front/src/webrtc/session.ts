import type { AppConfig } from "../config/appConfig";
import type { AssistantElements } from "../ui/elements";
import type { AudioState } from "../audio/audioState";
import { startMic, stopMic } from "../audio/mic";
import { negotiate } from "./negotiate";
import { createEnergyVad, type VadInstance } from "../audio/vad";
import { startWaveforms } from "../ui/waves";

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
  onSpeechActivityChange?: (active: boolean) => void,
  opts?: { sessionId?: string | null },
): Promise<string | null> {
  if (session) return null;

  const micStream = await startMic(audio);
  const peer = new RTCPeerConnection({
    iceServers: config.webrtc.iceServers,
    iceCandidatePoolSize: config.webrtc.iceCandidatePoolSize,
    bundlePolicy: config.webrtc.bundlePolicy,
    rtcpMuxPolicy: config.webrtc.rtcpMuxPolicy,
  });

  peer.ontrack = (e) => {
    if (el.remoteAudio) el.remoteAudio.srcObject = e.streams[0];
  };

  const track = micStream.getAudioTracks()[0];
  const sender = peer.addTrack(track, micStream);

  let vad: VadInstance | null = null;
  if (audio.vadEnabled) {
    vad = createEnergyVad(
      track,
      config,
      () => audio.vadThreshold,
      (v) => onVadText(`${v} dBFS`),
      onSpeechActivityChange,
    );
    await sender.replaceTrack(vad.track);
  }

  const waves = startWaveforms(el, config, micStream);

  const sessionId = await negotiate(peer, config, opts);

  session = { peer, sender, micStream, vad, wavesStop: waves.stop };
  return sessionId;
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

export function setMicEnabled(enabled: boolean): void {
  if (!session) return;
  const track = session.sender.track;
  if (track) track.enabled = enabled;
}
