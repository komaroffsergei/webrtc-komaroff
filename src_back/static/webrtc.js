(function(){
  async function createPeer(config){
    const pc = new RTCPeerConnection({ iceServers: config.webrtc.iceServers });
    if (config.webrtc.diagnostics){
      pc.oniceconnectionstatechange = () => console.log('[pc] iceconnectionstate:', pc.iceConnectionState);
      pc.onconnectionstatechange = () => console.log('[pc] connectionstate:', pc.connectionState);
      pc.onsignalingstatechange = () => console.log('[pc] signalingstate:', pc.signalingState);
      pc.onicegatheringstatechange = () => console.log('[pc] icegatheringstate:', pc.iceGatheringState);
      pc.onicecandidate = (e) => console.log('[pc] icecandidate:', !!e.candidate);
    }
    return pc;
  }

  async function waitForIceGatheringComplete(pc, timeoutMs = 3000){
    if (pc.iceGatheringState === 'complete') return;
    await new Promise((resolve) => {
      let done = false;
      const finish = () => { if (!done){ done = true; resolve(); } };
      const timer = setTimeout(finish, timeoutMs);
      pc.addEventListener('icegatheringstatechange', () => {
        if (pc.iceGatheringState === 'complete'){
          clearTimeout(timer);
          finish();
        }
      });
    });
  }

  async function negotiate(pc, config){
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    await waitForIceGatheringComplete(pc, 3000);
    const resp = await fetch(config.signaling.offerEndpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type })
    });
    const answer = await resp.json();
    await pc.setRemoteDescription(answer);
  }

  window.WebRTC = { createPeer, negotiate };
})();
