// Global configuration for the WebRTC demo
// Keep only environment- or tuning-related values here
(function () {
    window.AppConfig = {
        signaling: {
            // Non-trickle signaling: server replies with a finalized SDP answer (candidates embedded)
            offerEndpoint: '/offer'
        },
        webrtc: {
            // STUN/TURN servers used for ICE candidate gathering.
            // Prefer IP literal for STUN to skip DNS latency (replace with your STUN IP).
            iceServers: [
                {urls: ["stun:stun.gis-master.ru:3478"]}
                // { urls: [
                //   // Public STUNs for basic NAT traversal. Replace with your infra for production.
                //   "stun:stun.l.google.com:19302",
                //   "stun:stun1.l.google.com:19302",
                //   "stun:stun2.l.google.com:19302"
                // ] },
                // TURN is required for symmetric NAT / firewalled networks. Replace with your server:
                // { urls: ["turn:TURN_HOST:3478?transport=udp", "turn:TURN_HOST:3478?transport=tcp", "turns:TURN_HOST:5349?transport=tcp"], username: "user", credential: "pass" },
            ],
            // Pre-allocate ICE candidates to reduce time-to-connect.
            iceCandidatePoolSize: 4,
            // Use a single bundled transport for all media to simplify negotiation and reduce setup time.
            bundlePolicy: 'max-bundle',
            // Require RTCP multiplexing over the same transport (standard in modern WebRTC).
            rtcpMuxPolicy: 'require',
            // Force relay via TURN in restrictive networks (behind VPN / symmetric NAT)
            // Set to true when TURN is configured above.
            forceRelay: false,
            // Enable verbose diagnostics (state changes, candidates) to the on-page log.
            diagnostics: true,
            // Client-side fallback timeout for waiting ICE gathering completion
            iceGatherTimeoutMs: 1000
        },
        audio: {
            vad: {
                enabled: true,
                threshold: -55
            },
            // Default constraints for getUserMedia audio capture.
            input: {
                // Enable browser AEC (Acoustic Echo Cancellation) by default.
                echoCancellationDefault: true,
                // Enable browser Noise Suppression by default.
                noiseSuppressionDefault: true
            },
            // OPUS encoder tuning for uplink.
            opus: {
                // Target maximum OPUS bitrate in bits per second.
                // 24 kbps is a balanced default for mono voice @48kHz.
                maxBitrate: 24000 // bps
            },
            // Waveform visualizer/analyser settings for input/output scopes.
            analyser: {
                // FFT size for WebAudio AnalyserNode (power of two).
                fftSize: 1024,
                // Duration of history kept for drawing (seconds).
                historySeconds: 10
            },
            // Voice Activity Detector (energy-based) parameters.
            vad: {
                // FFT size for spectral energy measurement.
                fftSize: 2048,
                // Envelope attack time for gate (seconds).
                attackSeconds: 0.02,
                // Envelope release time for gate (seconds).
                releaseSeconds: 0.02
            }
        },
        ui: {
            canvas: {width: 400, height: 80},
            colors: {
                grid: "#ddd",
                in: "#2b8",
                out: "#82b"
            }
        }
    };
})();
