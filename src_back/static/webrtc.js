(function(){
  // Buffer for local candidates before clientId is known
  const pendingCandidates = [];

  function startServerTricklePolling(pc, config){
    if (!config?.signaling?.trickleGetEndpoint) return;
    const interval = setInterval(async ()=>{
      try{
        if (!window.__webrtcClientId) return;
        const url = `${config.signaling.trickleGetEndpoint}?clientId=${encodeURIComponent(window.__webrtcClientId)}`;
        const r = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
        if (!r.ok) return;
        const data = await r.json();
        const candidates = Array.isArray(data?.candidates) ? data.candidates : [];
        for (const c of candidates){
          try{ await pc.addIceCandidate(c); }catch(e){ console.warn('addIceCandidate failed', e); }
        }
      }catch(err){ /* ignore */ }
    }, 500);
    // Stop when connection closed
    pc.addEventListener('connectionstatechange', ()=>{
      if (pc.connectionState === 'failed' || pc.connectionState === 'closed'){
        clearInterval(interval);
      }
    });
  }

  // Create and configure RTCPeerConnection
  async function createPeer(config){
    const pc = new RTCPeerConnection({ iceServers: config.webrtc.iceServers });
    // Ensure we have a receiving audio m-line even if no local mic is added yet
    try{
      const hasSend = pc.getSenders().some(s => s.track && s.track.kind === 'audio');
      const hasRecv = pc.getTransceivers().some(t => t.receiver && t.receiver.track && t.receiver.track.kind === 'audio');
      if (!hasSend && !hasRecv){
        pc.addTransceiver('audio', { direction: 'recvonly' });
      }
    }catch{}
    if (config.webrtc.diagnostics){
      pc.oniceconnectionstatechange = () => { console.log('[pc] iceconnectionstate:', pc.iceConnectionState); window.AppLog && AppLog.emit('[pc] iceconnectionstate', pc.iceConnectionState); };
      pc.onconnectionstatechange = () => { console.log('[pc] connectionstate:', pc.connectionState); window.AppLog && AppLog.emit('[pc] connectionstate', pc.connectionState); };
      pc.onsignalingstatechange = () => { console.log('[pc] signalingstate:', pc.signalingState); window.AppLog && AppLog.emit('[pc] signalingstate', pc.signalingState); };
      pc.onicegatheringstatechange = () => { console.log('[pc] icegatheringstate:', pc.iceGatheringState); window.AppLog && AppLog.emit('[pc] icegatheringstate', pc.iceGatheringState); };
      pc.onicecandidate = (e) => { console.log('[pc] icecandidate:', !!e.candidate); window.AppLog && AppLog.emit('[pc] icecandidate', e && e.candidate ? e.candidate.candidate : null); };
    }
    // Trickle ICE: send local candidates to server as they appear
    pc.addEventListener('icecandidate', async (e) => {
      if (!e.candidate) return;
      const item = {
        candidate: e.candidate.candidate,
        sdpMid: e.candidate.sdpMid,
        sdpMLineIndex: e.candidate.sdpMLineIndex,
      };
      if (!window.__webrtcClientId){
        pendingCandidates.push(item);
        return;
      }
      try{
        await fetch(config.signaling.tricklePostEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ clientId: window.__webrtcClientId, candidates: [item] })
        });
      }catch(err){ console.warn('trickle POST failed', err); }
    });
    return pc;
  }

  // Create an offer, send it to the signaling server, and apply the received answer
  async function negotiate(pc, config){
    // 1) Create local offer and start ICE gathering
    await pc.setLocalDescription(await pc.createOffer());

    // 2) With trickle enabled, we don't need to wait for complete; send offer immediately
    // await waitForIceGatheringComplete(pc, 3000);

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
    // Save clientId to enable trickle and flush buffered local candidates
    window.__webrtcClientId = answer.clientId;
    try{
      if (Array.isArray(pendingCandidates) && pendingCandidates.length){
        await fetch(config.signaling.tricklePostEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ clientId: window.__webrtcClientId, candidates: pendingCandidates })
        });
        pendingCandidates.length = 0;
      }
    }catch(err){ console.warn('flush trickle failed', err); }
    // Start polling for server-side candidates
    startServerTricklePolling(pc, config);

    // 4) Set remote description
    await pc.setRemoteDescription(answer);

    // Optional: return the answer for debugging/inspection
    return answer;
  }

  window.WebRTC = { createPeer, negotiate };
})();
