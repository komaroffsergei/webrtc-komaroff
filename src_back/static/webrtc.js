(function(){
  // Buffer for local candidates before clientId is known
  const pendingCandidates = [];

  function startServerTricklePolling(pc, config){
    if (!config?.signaling?.trickleGetEndpoint) return;
    // Prevent duplicate intervals
    if (pc.__trickleInterval) { clearInterval(pc.__trickleInterval); }
    let idleRounds = 0;
    pc.__trickleInterval = setInterval(async ()=>{
      try{
        if (!window.__webrtcClientId) return;
        const url = `${config.signaling.trickleGetEndpoint}?clientId=${encodeURIComponent(window.__webrtcClientId)}`;
        const r = await fetch(url, { method: 'GET', headers: { 'Accept': 'application/json' } });
        if (!r.ok) return;
        const data = await r.json();
        const candidates = Array.isArray(data?.candidates) ? data.candidates : [];
        if (candidates.length === 0){
          idleRounds += 1;
        } else {
          idleRounds = 0;
        }
        for (const c of candidates){
          try{ await pc.addIceCandidate(c); }catch(e){ console.warn('addIceCandidate failed', e); }
        }
        // Auto-stop after connected and a few idle rounds (no new candidates)
        if ((pc.iceConnectionState === 'connected' || pc.iceConnectionState === 'completed') && idleRounds >= 3){
          clearInterval(pc.__trickleInterval);
          pc.__trickleInterval = null;
        }
      }catch(err){ /* ignore */ }
    }, 500);
    const stopIfDone = ()=>{
      if (pc.connectionState === 'connected' || pc.connectionState === 'failed' || pc.connectionState === 'closed'){
        if (pc.__trickleInterval){ clearInterval(pc.__trickleInterval); pc.__trickleInterval = null; }
      }
    };
    pc.addEventListener('connectionstatechange', stopIfDone);
    pc.addEventListener('iceconnectionstatechange', stopIfDone);
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
  // Wait until ICE gathering completes or timeout elapses
  async function waitForIceGatheringComplete(pc, timeoutMs = 100){
    if (pc.iceGatheringState === 'complete') return;
    await new Promise((resolve) => {
      let timer;
      const onChange = () => {
        if (pc.iceGatheringState === 'complete'){
          clearTimeout(timer);
          pc.removeEventListener('icegatheringstatechange', onChange);
          resolve();
        }
      };
      timer = setTimeout(() => {
        pc.removeEventListener('icegatheringstatechange', onChange);
        resolve();
      }, timeoutMs);
      pc.addEventListener('icegatheringstatechange', onChange);
    });
  }

  async function negotiate(pc, config){
    // 1) Create local offer and start ICE gathering
    await pc.setLocalDescription(await pc.createOffer());

    // 2) Short pre-wait to let srflx candidates appear in SDP for reliability in prod
    await waitForIceGatheringComplete(pc, 100);

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
    // Prefer WebSocket for server-side candidates; fallback to polling if WS fails
    try{
      const wsUrl = (location.protocol.replace('http', 'ws') + '//' + location.host + config.signaling.wsEndpoint + `?clientId=${encodeURIComponent(window.__webrtcClientId)}`);
      const ws = new WebSocket(wsUrl);
      ws.onmessage = async (ev) => {
        try{
          const msg = JSON.parse(ev.data);
          if (msg?.type === 'candidate'){
            await pc.addIceCandidate(msg);
          } else if (msg?.type === 'end-of-candidates'){
            // no-op; ICE will complete naturally
          }
        }catch(e){ /* ignore */ }
      };
      pc.addEventListener('icecandidate', (e)=>{
        if (!e.candidate) { try{ ws.send(JSON.stringify({ type: 'end-of-candidates' })); }catch{}; return; }
        try{
          ws.send(JSON.stringify({
            type: 'candidate',
            candidate: e.candidate.candidate,
            sdpMid: e.candidate.sdpMid,
            sdpMLineIndex: e.candidate.sdpMLineIndex,
          }));
        }catch{}
      });
      ws.onopen = () => { /* ready */ };
      ws.onerror = () => { try{ ws.close(); }catch{}; startServerTricklePolling(pc, config); };
      ws.onclose = () => { /* ended */ };
    }catch(err){ startServerTricklePolling(pc, config); }

    // 4) Set remote description
    await pc.setRemoteDescription(answer);

    // Optional: return the answer for debugging/inspection
    return answer;
  }

  window.WebRTC = { createPeer, negotiate };
})();
