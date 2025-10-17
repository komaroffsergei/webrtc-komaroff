(function(){
  // Local candidate buffer until clientId/WS become available
  const pendingCandidates = [];

  // Wait until ICE gathering completes or timeout elapses (short pre-wait for srflx)
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

  async function createPeer(config){
    const pc = new RTCPeerConnection({
      iceServers: config.webrtc.iceServers,
      iceCandidatePoolSize: config.webrtc.iceCandidatePoolSize || 4,
      bundlePolicy: config.webrtc.bundlePolicy || 'max-bundle',
      rtcpMuxPolicy: config.webrtc.rtcpMuxPolicy || 'require',
    });

    // Ensure we have a receiving audio m-line even if no local mic is added yet
    try{
      const hasSend = pc.getSenders().some(s => s.track && s.track.kind === 'audio');
      const hasRecv = pc.getTransceivers().some(t => t.receiver && t.receiver.track && t.receiver.track.kind === 'audio');
      if (!hasSend && !hasRecv){
        pc.addTransceiver('audio', { direction: 'recvonly' });
      }
    }catch{}

    // Diagnostics
    if (config.webrtc.diagnostics){
      pc.oniceconnectionstatechange = () => { console.log('[pc] iceconnectionstate:', pc.iceConnectionState); window.AppLog && AppLog.emit('[pc] iceconnectionstate', pc.iceConnectionState); };
      pc.onconnectionstatechange = () => { console.log('[pc] connectionstate:', pc.connectionState); window.AppLog && AppLog.emit('[pc] connectionstate', pc.connectionState); };
      pc.onsignalingstatechange = () => { console.log('[pc] signalingstate:', pc.signalingState); window.AppLog && AppLog.emit('[pc] signalingstate', pc.signalingState); };
      pc.onicegatheringstatechange = () => { console.log('[pc] icegatheringstate:', pc.iceGatheringState); window.AppLog && AppLog.emit('[pc] icegatheringstate', pc.iceGatheringState); };
      pc.onicecandidate = (e) => { console.log('[pc] icecandidate:', !!e.candidate); window.AppLog && AppLog.emit('[pc] icecandidate', e && e.candidate ? e.candidate.candidate : null); };
    }

    // Buffer candidates until WebSocket is ready
    pc.addEventListener('icecandidate', (e) => {
      if (!e.candidate) return;
      const item = {
        type: 'candidate',
        candidate: e.candidate.candidate,
        sdpMid: e.candidate.sdpMid,
        sdpMLineIndex: e.candidate.sdpMLineIndex,
      };
      // If WS is ready, send immediately; else buffer
      if (pc.__ws && pc.__ws.readyState === WebSocket.OPEN){
        try{ pc.__ws.send(JSON.stringify(item)); }catch{}
      } else {
        pendingCandidates.push(item);
      }
    });

    return pc;
  }

  async function negotiate(pc, config){
    // 1) Create local offer and start ICE gathering
    await pc.setLocalDescription(await pc.createOffer());

    // 2) Short pre-wait to let srflx candidates appear in SDP
    await waitForIceGatheringComplete(pc, 100);

    // 3) Send offer to signaling server and receive answer
    const { sdp, type } = pc.localDescription;
    const resp = await fetch(config.signaling.offerEndpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sdp, type })
    });
    if (!resp.ok){ throw new Error(`Signaling server responded with ${resp.status}`); }
    const answer = await resp.json();

    // 4) Open WebSocket for full-duplex trickle and flush buffered local candidates
    try{
      window.__webrtcClientId = answer.clientId;
      const wsUrl = (location.protocol.replace('http', 'ws') + '//' + location.host + config.signaling.wsEndpoint + `?clientId=${encodeURIComponent(window.__webrtcClientId)}`);
      const ws = new WebSocket(wsUrl);
      pc.__ws = ws;
      ws.onopen = () => {
        // Flush buffered
        try{
          while(pendingCandidates.length){
            ws.send(JSON.stringify(pendingCandidates.shift()));
          }
        }catch{}
      };
      ws.onmessage = async (ev) => {
        try{
          const msg = JSON.parse(ev.data);
          if (msg && msg.type === 'candidate'){
            await pc.addIceCandidate(msg);
          } else if (msg && msg.type === 'end-of-candidates'){
            // Optional: pc.addIceCandidate(null);
          }
        }catch(e){ /* ignore */ }
      };
      ws.onerror = () => { try{ ws.close(); }catch{} };
      ws.onclose = () => { pc.__ws = null; };
    }catch(err){ /* WS init failed */ }

    // 5) Apply remote answer
    await pc.setRemoteDescription(answer);
    return answer;
  }

  // Export API
  window.WebRTC = Object.freeze({ createPeer, negotiate });
})();
