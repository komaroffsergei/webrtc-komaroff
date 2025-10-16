(function(){
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
    return pc;
  }

  async function negotiate(pc, config){
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
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
    await pc.setRemoteDescription(answer);
    return answer;
  }

  window.WebRTC = { createPeer, negotiate };
})();