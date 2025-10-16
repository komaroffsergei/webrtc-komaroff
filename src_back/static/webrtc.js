(function(){
  // Create and configure RTCPeerConnection
  async function createPeer(config){
    // Create RTCPeerConnection with configured ICE servers
    const pc = new RTCPeerConnection({ iceServers: config.webrtc.iceServers });

    // Optional diagnostics logging to help with debugging connection states
    if (config.webrtc.diagnostics){
      pc.oniceconnectionstatechange = () => { console.log('[pc] iceconnectionstate:', pc.iceConnectionState); window.AppLog && AppLog.emit('[pc] iceconnectionstate', pc.iceConnectionState); };
      pc.onconnectionstatechange = () => { console.log('[pc] connectionstate:', pc.connectionState); window.AppLog && AppLog.emit('[pc] connectionstate', pc.connectionState); };
      pc.onsignalingstatechange = () => { console.log('[pc] signalingstate:', pc.signalingState); window.AppLog && AppLog.emit('[pc] signalingstate', pc.signalingState); };
      pc.onicegatheringstatechange = () => { console.log('[pc] icegatheringstate:', pc.iceGatheringState); window.AppLog && AppLog.emit('[pc] icegatheringstate', pc.iceGatheringState); };
      pc.onicecandidate = (e) => { console.log('[pc] icecandidate:', !!e.candidate); window.AppLog && AppLog.emit('[pc] icecandidate', e && e.candidate ? e.candidate.candidate : null); };
    }
    return pc;
  }

  // Wait until ICE gathering completes or the timeout elapses
  async function waitForIceGatheringComplete(pc, timeoutMs = 3000){
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
    // 1) Create local offer and start ICE gathering
    await pc.setLocalDescription(await pc.createOffer());

    // 2) Wait for ICE candidates (or timeout)
    await waitForIceGatheringComplete(pc, 3000);

    // 3) Send offer to signaling server and receive answer
    const { sdp, type } = pc.localDescription;
    const resp = await fetch(config.signaling.offerEndpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sdp, type })
    });
    if (!resp.ok) {
      throw new Error(`Signaling server responded with ${resp.status}`);
    }
    const answer = await resp.json();

    // 4) Set remote description
    await pc.setRemoteDescription(answer);

    // Optional: return the answer for debugging/inspection
    return answer;
  }

  window.WebRTC = { createPeer, negotiate };
})();
