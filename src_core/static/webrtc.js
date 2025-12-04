(function () {
    const emitLog = typeof window.logEvent === 'function' ? window.logEvent : () => false;
    const SERVICE = 'webrtc';

    // Wait until ICE gathering completes or timeout elapses
    async function waitForIceGatheringComplete(pc, timeoutMs = 3000) {
        if (pc.iceGatheringState === 'complete') return;
        await new Promise((resolve) => {
            let timer;
            const onChange = () => {
                if (pc.iceGatheringState === 'complete') {
                    clearTimeout(timer);
                    pc.removeEventListener('icegatheringstatechange', onChange);
                    setTimeout(() => resolve())
                }
            };
            timer = setTimeout(() => {
                pc.removeEventListener('icegatheringstatechange', onChange);
                resolve();
            }, timeoutMs);
            pc.addEventListener('icegatheringstatechange', onChange);
        });



        //  return new Promise((resolve) => {
        //     if (pc.iceGatheringState === 'complete') {
        //         resolve();
        //     } else {
        //         function checkState() {
        //             if (pc.iceGatheringState === 'complete') {
        //                 pc.removeEventListener('icegatheringstatechange', checkState);
        //                 resolve();
        //             }
        //         }
        //         pc.addEventListener('icegatheringstatechange', checkState);
        //     }
        // });
    }






/*    function waitForIceGatheringComplete(pc, timeoutMs = 1500) {
        if (pc.iceGatheringState === 'complete') return Promise.resolve();
        return new Promise((resolve) => {
            const onState = () => {
                if (pc.iceGatheringState === 'complete') {
                    cleanup();
                    resolve();
                }
            };
            const onCandidate = (e) => {
                if (!e.candidate) {
                    cleanup();
                    resolve();
                }
            };
            const cleanup = () => {
                clearTimeout(timer);
                pc.removeEventListener('icegatheringstatechange', onState);
                pc.removeEventListener('icecandidate', onCandidate);
            };
            const timer = setTimeout(() => {
                cleanup();
                resolve();
            }, timeoutMs);
            pc.addEventListener('icegatheringstatechange', onState);
            pc.addEventListener('icecandidate', onCandidate);
        });
    }*/


    async function createPeer(config) {
        const pc = new RTCPeerConnection({
            iceServers: config.webrtc.iceServers,
            iceCandidatePoolSize: config.webrtc.iceCandidatePoolSize || 4,
            bundlePolicy: config.webrtc.bundlePolicy || 'max-bundle',
            rtcpMuxPolicy: config.webrtc.rtcpMuxPolicy || 'require',
            iceTransportPolicy: (config.webrtc.forceRelay ? 'relay' : undefined),
        });
        // Low-latency hint for Chromium-based browsers
        try {
            pc.setConfiguration({...pc.getConfiguration(), sdpSemantics: 'unified-plan'});
        } catch {
        }

        // Ensure we have a receiving audio m-line even if no local mic is added yet
        try {
            const hasSend = pc.getSenders().some(s => s.track && s.track.kind === 'audio');
            const hasRecv = pc.getTransceivers().some(t => t.receiver && t.receiver.track && t.receiver.track.kind === 'audio');
            if (!hasSend && !hasRecv) {
                pc.addTransceiver('audio', {direction: 'recvonly'});
            }
        } catch {
        }

        // Diagnostics
        if (config.webrtc.diagnostics) {
            const emitState = (label, value) => {
                emitLog({service: SERVICE, type: 'info', message: `[pc] ${label}: ${value}`});
            };
            pc.oniceconnectionstatechange = () => emitState('iceconnectionstate', pc.iceConnectionState);
            pc.onconnectionstatechange = () => emitState('connectionstate', pc.connectionState);
            pc.onsignalingstatechange = () => emitState('signalingstate', pc.signalingState);
            pc.onicegatheringstatechange = () => emitState('icegatheringstate', pc.iceGatheringState);
        }

        return pc;
    }

    async function negotiate(pc, config) {
        // 1) Create local offer and wait for full ICE gathering (non-trickle)
        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);
        await waitForIceGatheringComplete(pc, config.webrtc.iceGatherTimeoutMs);

        // 2) Send offer to signaling server and receive answer
        const {sdp, type} = pc.localDescription;
        const resp = await fetch(config.signaling.offerEndpoint, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({sdp, type})
        });
        if (!resp.ok) {
            throw new Error(`Signaling server responded with ${resp.status}`);
        }
        const answer = await resp.json();

        // 3) Apply remote answer
        await pc.setRemoteDescription(answer);
        return answer;
    }

    // Export API
    window.WebRTC = Object.freeze({createPeer, negotiate});
})();
