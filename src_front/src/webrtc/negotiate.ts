import type { AppConfig } from "../config/appConfig";

export async function negotiate(
  pc: RTCPeerConnection,
  config: AppConfig,
  opts?: { sessionId?: string | null },
): Promise<string | null> {
  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  await waitIceGather(pc, config.webrtc.iceGatherTimeoutMs);

  const local = pc.localDescription;
  if (!local) throw new Error("localDescription is missing");

  const body: Record<string, unknown> = { sdp: local.sdp, type: local.type };
  const sessionId = opts?.sessionId;
  if (typeof sessionId === "string" && sessionId) body.session_id = sessionId;

  const resp = await fetch(config.signaling.offerEndpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!resp.ok) throw new Error(`Signaling server responded with ${resp.status}`);

  const answer = (await resp.json()) as any;
  const sdp = typeof answer?.sdp === "string" ? answer.sdp : null;
  const type = typeof answer?.type === "string" ? answer.type : null;
  if (!sdp || !type) throw new Error("Signaling answer is missing sdp/type");
  await pc.setRemoteDescription({ sdp, type });

  return typeof answer?.session_id === "string" ? answer.session_id : null;
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
