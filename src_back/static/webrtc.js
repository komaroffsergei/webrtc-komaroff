(function(){
  // Create and configure RTCPeerConnection
  async function createPeer(config){
    // Pre-warm ICE with pool, aggressive bundling
    const pc = new RTCPeerConnection({
      iceServers: config.webrtc.iceServers,
      iceCandidatePoolSize: config.webrtc.iceCandidatePoolSize || 4,
      bundlePolicy: config.webrtc.bundlePolicy || 'max-bundle',
      rtcpMuxPolicy: config.webrtc.rtcpMuxPolicy || 'require',
    });
    // Reserve audio transceiver early
    let audioTransceiver = null;
    try { audioTransceiver = pc.addTransceiver('audio', { direction: 'sendrecv' }); } catch{}
    // Prefer OPUS via codec preferences (safe alternative to SDP rewriting)
    try {
      const caps = RTCRtpSender.getCapabilities && RTCRtpSender.getCapabilities('audio');
      if (caps && Array.isArray(caps.codecs)){
        const opusFirst = caps.codecs.filter(c => /opus/i.test(c.mimeType));
        if (opusFirst.length){
          const t = audioTransceiver || pc.getTransceivers().find(tr => tr.receiver?.track?.kind === 'audio' || tr.sender?.track?.kind === 'audio');
          if (t && t.setCodecPreferences){ t.setCodecPreferences(opusFirst); }
        }
      }
    } catch {}

    // Optional diagnostics logging to help with debugging connection states
    if (config.webrtc.diagnostics){
      pc.oniceconnectionstatechange = () => { console.log('[pc] iceconnectionstate:', pc.iceConnectionState); window.AppLog && AppLog.emit('[pc] iceconnectionstate', pc.iceConnectionState); };
      pc.onconnectionstatechange = () => { console.log('[pc] connectionstate:', pc.connectionState); window.AppLog && AppLog.emit('[pc] connectionstate', pc.connectionState); };
      pc.onsignalingstatechange = () => { console.log('[pc] signalingstate:', pc.signalingState); window.AppLog && AppLog.emit('[pc] signalingstate', pc.signalingState); };
      pc.onicegatheringstatechange = () => { console.log('[pc] icegatheringstate:', pc.iceGatheringState); window.AppLog && AppLog.emit('[pc] icegatheringstate', pc.iceGatheringState); };
      pc.onicecandidate = (e) => {
        const c = e && e.candidate ? e.candidate.candidate : null;
        if (!c) { window.AppLog && AppLog.emit('[pc] icecandidate', null); return; }
        // filter to speedup: only IPv4 UDP
        if (c.includes(' udp ') && /\s\d+\.\d+\.\d+\.\d+\s/.test(c)){
          window.AppLog && AppLog.emit('[pc] icecandidate', c);
        } else {
          // ignore TCP and IPv6 to reduce negotiation noise
          return;
        }
      };
    }
    return pc;
  }

  // Wait until ICE gathering completes or the timeout elapses (short timeout for faster offer)
  async function waitForIceGatheringComplete(pc, timeoutMs = 400){
    if (pc.iceGatheringState === 'complete') return;
    await new Promise((resolve) => {
      let timer;
      const onChange = () => {
        if (pc.iceGatheringState === 'complete'){
          clearTimeout(timer);
          resolve();
        }
      };
      timer = setTimeout(() => {
        pc.removeEventListener('icegatheringstatechange', onChange);
        resolve(); // proceed even if not fully complete
      }, timeoutMs);
      pc.addEventListener('icegatheringstatechange', onChange, { once: true });
    });
  }

  // Create an offer, send it to the signaling server, and apply the received answer
  async function negotiate(pc, config){
  // 1) Create and set local offer IMMEDIATELY
  const offer = await pc.createOffer({ offerToReceiveAudio: true });
  await pc.setLocalDescription(offer);

  // 2) SEND OFFER RIGHT AWAY — no waiting!
  const resp = await fetch(config.signaling.offerEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sdp: offer.sdp, type: offer.type })
  });

  if (!resp.ok) throw new Error(`Signaling server responded with ${resp.status}`);
  const answer = await resp.json();
  await pc.setRemoteDescription(answer);

  // 3) OPTIONAL: всё ещё можно ждать кандидаты для логгирования, но НЕ для отправки
  // (это уже не влияет на скорость handshake)
  return answer;
}
  window.WebRTC = { createPeer, negotiate };
})();
