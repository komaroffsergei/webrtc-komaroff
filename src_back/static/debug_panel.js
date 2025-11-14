/**
 * Simple debug panel showing SSE logs in unified format.
 * Expected payload: { time, service, type, message }.
 */
(function () {
    'use strict';

    const MAX_LOGS = 500;

    let panel = null;
    let toggleButton = null;
    let logContainer = null;
    let logs = [];
    let renderedCount = 0;

    function init() {
        createPanel();
        attachEvents();
    }

    function createPanel() {
        panel = document.createElement('div');
        panel.id = 'debugPanel';
        panel.className = 'debug-panel';

        const header = document.createElement('div');
        header.className = 'debug-header';

        const title = document.createElement('h3');
        title.textContent = 'DEBUG';
        header.appendChild(title);

        toggleButton = document.createElement('button');
        toggleButton.className = 'debug-toggle';
        toggleButton.textContent = '−';
        toggleButton.title = 'Свернуть/Развернуть';
        header.appendChild(toggleButton);

        const clearButton = document.createElement('button');
        clearButton.className = 'clear-btn';
        clearButton.textContent = 'Очистить';
        clearButton.addEventListener('click', clearLogs);
        header.appendChild(clearButton);

        panel.appendChild(header);

        logContainer = document.createElement('div');
        logContainer.className = 'debug-logs';
        panel.appendChild(logContainer);

        document.body.appendChild(panel);
    }

    function attachEvents() {
        if (!toggleButton) {
            return;
        }
        toggleButton.addEventListener('click', togglePanel);
    }

    function isValid(entry) {
        return (
            entry &&
            typeof entry.time === 'string' &&
            typeof entry.service === 'string' &&
            typeof entry.type === 'string'
        );
    }

    function addLog(entry) {
        if (!isValid(entry)) {
            console.warn('Unknown message format', entry)
            return;
        }

        logs.push(entry);
        if (logs.length > MAX_LOGS) {
            logs = logs.slice(-MAX_LOGS);
            renderedCount = 0;
            renderLogs(true);
            return;
        }

        renderLogs();
    }

    function formatLine(entry) {
        const timeLabel = new Date(entry.time).toLocaleTimeString();
        const service = entry.service || 'unknown';
        const typeLabel = entry.type.toUpperCase();
        return `[${timeLabel}] [${service}] [${typeLabel}] ${entry?.name ? [entry.name] : ''} ${entry.message}`;
    }

    function createRow(entry) {
        const row = document.createElement('div');
        row.className = `debug-log-entry log-level-${entry?.type || 'info'} log-name-${entry?.name || 'none'}`;
        row.textContent = formatLine(entry);
        return row;
    }

    function renderLogs(fullRefresh = false) {
        if (!logContainer) {
            return;
        }

        if (fullRefresh) {
            logContainer.innerHTML = '';
            renderedCount = 0;
        }

        for (let i = renderedCount; i < logs.length; i++) {
            logContainer.appendChild(createRow(logs[i]));
        }

        renderedCount = logs.length;
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function clearLogs() {
        logs = [];
        renderedCount = 0;
        if (logContainer) {
            logContainer.innerHTML = '';
        }
    }

    function togglePanel() {
        if (!panel) return;
        panel.classList.toggle('collapsed');
        if (toggleButton) {
            toggleButton.textContent = panel.classList.contains('collapsed') ? '+' : '−';
        }
    }

    function getStats() {
        return {
            total: logs.length,
            byType: logs.reduce((acc, entry) => {
                acc[entry.type] = (acc[entry.type] || 0) + 1;
                return acc;
            }, {})
        };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.DebugPanel = Object.freeze({
        addLog,
        clearLogs,
        getStats,
        togglePanel
    });
})();
