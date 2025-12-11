import type { AppConfig } from "../config/appConfig";
import { logEvent } from "./logging";

async function waitForIceGatheringComplete(
  pc: RTCPeerConnection,
  timeoutMs: number,
): Promise<void> {
  if (pc.iceGatheringState === "complete") {
    return;
  }

  await new Promise<void>((resolve) => {
    let timer: number | undefined;
    const onChange = () => {
      if (pc.iceGatheringState === "complete") {
        if (timer) {
          clearTimeout(timer);
        }
        pc.removeEventListener("icegatheringstatechange", onChange);
        resolve();
      }
    };
    timer = window.setTimeout(() => {
      pc.removeEventListener("icegatheringstatechange", onChange);
      resolve();
    }, timeoutMs);
    pc.addEventListener("icegatheringstatechange", onChange);
  });
}

export async function createPeer(config: AppConfig): Promise<RTCPeerConnection> {
  const pc = new RTCPeerConnection({
    iceServers: config.webrtc.iceServers,
    iceCandidatePoolSize: config.webrtc.iceCandidatePoolSize,
    bundlePolicy: config.webrtc.bundlePolicy,
    rtcpMuxPolicy:
      config.webrtc.rtcpMuxPolicy === "require" ? "require" : undefined,
    iceTransportPolicy: config.webrtc.forceRelay ? "relay" : undefined,
  });

  try {
    const cfg = pc.getConfiguration() as RTCConfiguration & {
      sdpSemantics?: string;
    };
    cfg.sdpSemantics = "unified-plan";
    pc.setConfiguration(cfg);
  } catch {
    /* ignore */
  }

  if (config.webrtc.diagnostics) {
    const emitState = (label: string, value: string) => {
      logEvent({
        service: "webrtc",
        type: "info",
        message: `[pc] ${label}: ${value}`,
      });
    };
    pc.oniceconnectionstatechange = () =>
      emitState("iceconnectionstate", pc.iceConnectionState);
    pc.onconnectionstatechange = () =>
      emitState("connectionstate", pc.connectionState);
    pc.onsignalingstatechange = () =>
      emitState("signalingstate", pc.signalingState);
    pc.onicegatheringstatechange = () =>
      emitState("icegatheringstate", pc.iceGatheringState);
  }

  return pc;
}

export async function negotiate(
  pc: RTCPeerConnection,
  config: AppConfig,
): Promise<void> {
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await waitForIceGatheringComplete(pc, config.webrtc.iceGatherTimeoutMs);

  const local = pc.localDescription;
  if (!local) {
    throw new Error("localDescription is missing");
  }

  const resp = await fetch(config.signaling.offerEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sdp: local.sdp, type: local.type }),
  });

  if (!resp.ok) {
    throw new Error(`Signaling server responded with ${resp.status}`);
  }

  const answer = await resp.json();
  await pc.setRemoteDescription(answer);
}
