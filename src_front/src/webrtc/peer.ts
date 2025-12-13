import type { AppConfig } from "../config/appConfig";

export function createPeer(config: AppConfig): RTCPeerConnection {
  return new RTCPeerConnection({
    iceServers: config.webrtc.iceServers,
    iceCandidatePoolSize: config.webrtc.iceCandidatePoolSize,
    bundlePolicy: config.webrtc.bundlePolicy,
    rtcpMuxPolicy: config.webrtc.rtcpMuxPolicy,
  });
}
