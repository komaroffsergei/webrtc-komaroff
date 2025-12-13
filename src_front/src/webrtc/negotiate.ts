import type { AppConfig } from "../config/appConfig";

export async function negotiate(pc: RTCPeerConnection, config: AppConfig): Promise<void> {
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  await waitIceGather(pc, config.webrtc.iceGatherTimeoutMs);

  const local = pc.localDescription;
  if (!local) throw new Error("localDescription is missing");

  const resp = await fetch(config.signaling.offerEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sdp: local.sdp, type: local.type }),
  });

  if (!resp.ok) throw new Error(`Signaling server responded with ${resp.status}`);

  const answer = await resp.json();
  await pc.setRemoteDescription(answer);
}

function waitIceGather(pc: RTCPeerConnection, timeoutMs: number): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();

  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      pc.removeEventListener("icegatheringstatechange", onChange);
      resolve();
    }, timeoutMs);

    const onChange = () => {
      if (pc.iceGatheringState === "complete") {
        window.clearTimeout(timer);
        pc.removeEventListener("icegatheringstatechange", onChange);
        resolve();
      }
    };

    pc.addEventListener("icegatheringstatechange", onChange);
  });
}
