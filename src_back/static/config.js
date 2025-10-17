// Global configuration for the WebRTC demo
// Keep only environment- or tuning-related values here
(function(){
  window.AppConfig = {
    signaling: {
      offerEndpoint: '/offer',
      // WebSocket endpoint for incremental candidate exchange (full-duplex trickle)
      wsEndpoint: '/ws'
    },
    webrtc: {
      // STUN/TURN servers used for ICE candidate gathering.
      // Prefer IP literal for STUN to skip DNS latency (replace with your STUN IP).
      iceServers: [
        { urls: ["stun:stun.gis-master.ru:3478"] }, // original: stun:stun.gis-master.ru:3478 // stun:178.20.41.87:3478
        // If direct P2P fails in some networks, enable TURN by adding your relays:
        // { urls: ["turn:turn.example.com:3478?transport=udp", "turn:turn.example.com:3478?transport=tcp"], username: "user", credential: "pass" },
      ],
      // Pre-allocate ICE candidates to reduce time-to-connect.
      iceCandidatePoolSize: 4,
      // Use a single bundled transport for all media to simplify negotiation and reduce setup time.
      bundlePolicy: 'max-bundle',
      // Require RTCP multiplexing over the same transport (standard in modern WebRTC).
      rtcpMuxPolicy: 'require',
      // Enable verbose diagnostics (state changes, candidates) to the on-page log.
      diagnostics: true
    },
    audio: {
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
      canvas: { width: 400, height: 80 },
      colors: {
        grid: "#ddd",
        in: "#2b8",
        out: "#82b"
      }
    }
  };
})();
