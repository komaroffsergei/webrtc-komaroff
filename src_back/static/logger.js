(function () {
    'use strict';


    function emit(payload) {
        if (!payload) {
            return false;
        }

        if (!payload.time) {
            payload.time = new Date().toISOString();
        }

        if (window.DebugPanel && typeof window.DebugPanel.addLog === 'function') {
            window.DebugPanel.addLog(payload);
            return true;
        }

        let writer;
        if (console[payload.type]) {
            writer = console[payload.type]
        } else {
            writer = console.log
        }
        writer(`${payload.time} [${payload.service}] [${payload.type}] ${payload.message}`);
        return true;
    }

    window.logEvent = function logEvent(entry) {
        if (Array.isArray(entry)) {
            return entry.map(logEvent).some(Boolean);
        }
        return emit(entry);
    };
})();
