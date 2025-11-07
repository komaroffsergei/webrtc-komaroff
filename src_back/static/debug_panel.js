/**
 * Debug Panel - панель отладки для логирования всех SSE событий
 */

(function() {
    'use strict';

    let debugPanel = null;
    let logContainer = null;
    let toggleButton = null;
    let filterButtons = {};
    let clearButton = null;
    let logs = [];
    let maxLogs = 500;
    
    // Фильтры по типам
    let activeFilters = {
        'command': true,
        'log': true,
        'message': true,
        'warning': true
    };
    
    // Фильтры по уровню логов
    let activeLevels = {
        'debug': true,
        'info': true,
        'warning': true,
        'error': true
    };
    
    // Фильтры по категориям
    let activeCategories = {
        'system': true,
        'webrtc': true,
        'nats': true,
        'audio': true,
        'whisper': true,
        'general': true
    };

    function init() {
        createDebugPanel();
        attachEventListeners();
    }

    function toNumber(value) {
        if (typeof value === 'number' && Number.isFinite(value)) {
            return value;
        }
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function formatSeconds(value) {
        const num = toNumber(value);
        if (num === null) {
            return null;
        }
        return `${num.toFixed(2)}s`;
    }

    function formatNumber(value) {
        const num = toNumber(value);
        if (num === null) {
            return null;
        }
        return num.toLocaleString();
    }

    function truncateText(text, limit = 80) {
        if (!text) {
            return '';
        }
        return text.length > limit ? `${text.slice(0, limit)}…` : text;
    }

    function describeWhisperEvent(eventType, data) {
        if (!eventType || !data) {
            return null;
        }
        const phraseId = data.phrase_id || '—';
        const duration = formatSeconds(data.audio_duration);
        const transTime = formatSeconds(data.transcription_time);
        const start = data.start || data.start_timestamp;
        const end = data.end || data.end_timestamp;
        const sr = formatNumber(data.sample_rate);
        const samples = formatNumber(data.audio_samples);
        const textPreview = data.text ? `"${truncateText(data.text, 80)}"` : null;

        switch (eventType) {
            case 'phrase_received': {
                let message = `Phrase RECEIVED [${phraseId}]`;
                if (duration) {
                    message += ` | audio: ${duration}`;
                }
                if (sr) {
                    message += ` | sr: ${sr} Hz`;
                }
                if (samples) {
                    message += ` | samples: ${samples}`;
                }
                return message;
            }
            case 'transcription_started': {
                let message = `Transcription STARTED [${phraseId}]`;
                if (duration) {
                    message += ` | audio: ${duration}`;
                }
                if (start) {
                    message += ` | start: ${new Date(start).toLocaleTimeString()}`;
                }
                return message;
            }
            case 'transcription_completed': {
                let message = `Transcription COMPLETED [${phraseId}]`;
                if (duration) {
                    message += ` | audio: ${duration}`;
                }
                if (transTime) {
                    message += ` | time: ${transTime}`;
                }
                const rtf = toNumber(data.rtf ?? (data.audio_duration && data.transcription_time ? data.transcription_time / data.audio_duration : null));
                if (rtf !== null) {
                    message += ` | RTF: ${rtf.toFixed(2)}x`;
                }
                if (typeof data.segments === 'number') {
                    message += ` | segments: ${data.segments}`;
                }
                if (start && end) {
                    message += ` | ${new Date(start).toLocaleTimeString()} → ${new Date(end).toLocaleTimeString()}`;
                }
                if (textPreview) {
                    message += ` | text: ${textPreview}`;
                }
                return message;
            }
            default: {
                if (eventType.includes('error') || eventType.includes('failed')) {
                    const errorType = data.error_type || 'Error';
                    const errorMsg = data.error_message || data.message;
                    const errPhrase = data.phrase_id || phraseId;
                    return `Transcription ERROR [${errPhrase}] ${errorType}: ${errorMsg}`;
                }
                return null;
            }
        }
    }

    function createDebugPanel() {
        // Создаем контейнер отладки
        debugPanel = document.createElement('div');
        debugPanel.id = 'debugPanel';
        debugPanel.className = 'debug-panel';
        
        // Заголовок
        const header = document.createElement('div');
        header.className = 'debug-header';
        
        const title = document.createElement('h3');
        title.textContent = 'DEBUG';
        header.appendChild(title);
        
        // Кнопка сворачивания
        toggleButton = document.createElement('button');
        toggleButton.className = 'debug-toggle';
        toggleButton.textContent = '−';
        toggleButton.title = 'Свернуть/Развернуть';
        header.appendChild(toggleButton);
        
        debugPanel.appendChild(header);
        
        // Фильтры по типу
        const typeFilters = document.createElement('div');
        typeFilters.className = 'debug-filters';
        typeFilters.innerHTML = '<span class="filter-label">Тип:</span>';
        
        ['command', 'log', 'message', 'warning'].forEach(type => {
            const btn = document.createElement('button');
            btn.className = 'filter-btn active';
            btn.textContent = type;
            btn.dataset.type = type;
            btn.onclick = () => toggleTypeFilter(type, btn);
            typeFilters.appendChild(btn);
            filterButtons[type] = btn;
        });
        
        debugPanel.appendChild(typeFilters);
        
        // Фильтры по уровню (только для логов)
        const levelFilters = document.createElement('div');
        levelFilters.className = 'debug-filters';
        levelFilters.innerHTML = '<span class="filter-label">Уровень:</span>';
        
        ['debug', 'info', 'warning', 'error'].forEach(level => {
            const btn = document.createElement('button');
            btn.className = 'filter-btn filter-level active';
            btn.textContent = level;
            btn.dataset.level = level;
            btn.onclick = () => toggleLevelFilter(level, btn);
            levelFilters.appendChild(btn);
        });
        
        debugPanel.appendChild(levelFilters);
        
        // Фильтры по категории
        const categoryFilters = document.createElement('div');
        categoryFilters.className = 'debug-filters';
        categoryFilters.innerHTML = '<span class="filter-label">Категория:</span>';
        
        ['system', 'webrtc', 'nats', 'audio', 'whisper', 'general'].forEach(category => {
            const btn = document.createElement('button');
            btn.className = 'filter-btn filter-category active';
            btn.textContent = category;
            btn.dataset.category = category;
            btn.onclick = () => toggleCategoryFilter(category, btn);
            categoryFilters.appendChild(btn);
        });
        
        debugPanel.appendChild(categoryFilters);
        
        // Кнопка очистки
        // const controls = document.createElement('div');
        // controls.className = 'debug-controls';
        //
        // clearButton = document.createElement('button');
        // clearButton.className = 'clear-btn';
        // clearButton.textContent = 'Очистить';
        // clearButton.onclick = clearLogs;
        // controls.appendChild(clearButton);
        //
        // debugPanel.appendChild(controls);
        
        // Контейнер для логов
        logContainer = document.createElement('div');
        logContainer.className = 'debug-logs';
        debugPanel.appendChild(logContainer);
        
        // Добавляем на страницу
        document.body.appendChild(debugPanel);
    }

    function attachEventListeners() {
        if (toggleButton) {
            toggleButton.addEventListener('click', togglePanel);
        }
    }

    function togglePanel() {
        debugPanel.classList.toggle('collapsed');
        toggleButton.textContent = debugPanel.classList.contains('collapsed') ? '+' : '−';
    }

    function toggleTypeFilter(type, button) {
        activeFilters[type] = !activeFilters[type];
        button.classList.toggle('active');
        renderLogs();
    }

    function toggleLevelFilter(level, button) {
        activeLevels[level] = !activeLevels[level];
        button.classList.toggle('active');
        renderLogs();
    }

    function toggleCategoryFilter(category, button) {
        activeCategories[category] = !activeCategories[category];
        button.classList.toggle('active');
        renderLogs();
    }

    function addLog(event) {
        const timestamp = event.timestamp || new Date().toISOString();
        const serviceName = event.service || 'src_server';
        event.service = serviceName;
        const logEntry = {
            timestamp,
            type: event.type || 'unknown',
            level: event.level || 'info',
            category: event.category || 'general',
            uid: event.uid,
            service: serviceName,
            data: event
        };
        
        logs.push(logEntry);
        
        // Ограничиваем количество логов
        if (logs.length > maxLogs) {
            logs = logs.slice(-maxLogs);
        }
        
        renderLogs();
    }

    function renderLogs() {
        if (!logContainer) return;
        
        logContainer.innerHTML = '';
        
        const filteredLogs = logs.filter(log => {
            // Фильтр по типу
            if (!activeFilters[log.type]) return false;
            
            // Фильтр по уровню (только для логов)
            if (log.type === 'log' && !activeLevels[log.level]) return false;
            
            // Фильтр по категории (только для логов)
            if (log.type === 'log' && !activeCategories[log.category]) return false;
            
            return true;
        });
        
        filteredLogs.forEach(log => {
            const logEl = document.createElement('div');
            logEl.className = `debug-log-entry log-${log.type} log-level-${log.level}`;
            
            const time = new Date(log.timestamp).toLocaleTimeString();
            const serviceTag = log.service || log.data?.service || 'src_server';
            const prefix = `[${time}] [${serviceTag}]`;
            
            let content = '';
            
            if (log.type === 'log') {
                let message = log.data.message;
                const eventType = log.data.event;
                
                // Специальное форматирование для логов транскрипции Whisper
                if (log.category === 'whisper') {
                    const eventMessage = describeWhisperEvent(eventType, log.data);
                    if (eventMessage) {
                        message = eventMessage;
                    } else if (message) {
                        // Используем структурированные данные из NatsLogger, если доступны (обратная совместимость)
                        if (message.includes('Transcription started:')) {
                            const audioDuration = log.data.audio_duration || parseFloat((message.match(/audio_duration=([\d.]+)s/) || [])[1]);
                            const audioBytes = log.data.audio_bytes || parseInt((message.match(/bytes=(\d+)/) || [])[1], 10);

                            if (audioDuration) {
                                message = `Transcription STARTED | audio: ${Number(audioDuration).toFixed(2)}s`;
                                if (audioBytes) {
                                    message += ` | size: ${(audioBytes / 1024).toFixed(1)}KB`;
                                }
                            }
                        } else if (message.includes('Transcription completed:')) {
                            // Приоритет структурированным данным из extra полей
                            const audioDuration = log.data.audio_duration || parseFloat((message.match(/audio_duration=([\d.]+)s/) || [])[1]);
                            const transTime = log.data.transcription_time || parseFloat((message.match(/transcription_time=([\d.]+)s/) || [])[1]);
                            const segments = log.data.segments || parseInt((message.match(/segments=(\d+)/) || [])[1], 10);
                            const rtf = log.data.rtf;
                            const startTimestamp = log.data.start || (message.match(/start=([\d\-:.TZ]+)/) || [])[1];
                            const endTimestamp = log.data.end || (message.match(/end=([\d\-:.TZ]+)/) || [])[1];
                            const text = log.data.text;

                            if (audioDuration && transTime) {
                                const calculatedRtf = rtf || (audioDuration > 0 ? (transTime / audioDuration) : 0);

                                let timeInfo = '';
                                if (startTimestamp && endTimestamp) {
                                    const startTime = new Date(startTimestamp).toLocaleTimeString();
                                    const endTime = new Date(endTimestamp).toLocaleTimeString();
                                    timeInfo = ` | ${startTime} -> ${endTime}`;
                                }

                                message = `Transcription COMPLETED | audio: ${Number(audioDuration).toFixed(2)}s | time: ${Number(transTime).toFixed(2)}s | RTF: ${Number(calculatedRtf).toFixed(2)}x | segments: ${segments || 0}${timeInfo}`;

                                if (text) {
                                    message += ` | text: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"`;
                                }
                            }
                        }
                    }
                }
                
                content = `${prefix} [${log.level.toUpperCase()}] [${log.category}] ${message}`;
            } else if (log.type === 'command') {
                content = `${prefix} [COMMAND] ${log.data.method} ${JSON.stringify(log.data.params || {})}`;
            } else if (log.type === 'message') {
                content = `${prefix} [MESSAGE] [${log.data.descr}] ${log.data.text}`;
            } else if (log.type === 'warning') {
                content = `${prefix} [WARNING] ${log.data.descr}`;
            } else {
                content = `${prefix} ${JSON.stringify(log.data)}`;
            }
            
            logEl.textContent = content;
            logEl.title = `UID: ${log.uid}\nClick to view full data`;
            logEl.onclick = () => showLogDetails(log);
            
            logContainer.appendChild(logEl);
        });
        
        // Автоскролл вниз
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    function showLogDetails(log) {
        const details = JSON.stringify(log.data, null, 2);
        const modal = document.createElement('div');
        modal.className = 'debug-modal';
        modal.innerHTML = `
            <div class="debug-modal-content">
                <h3>Детали события</h3>
                <pre>${details}</pre>
                <button onclick="this.closest('.debug-modal').remove()">Закрыть</button>
            </div>
        `;
        modal.onclick = (e) => {
            if (e.target === modal) modal.remove();
        };
        document.body.appendChild(modal);
    }

    function clearLogs() {
        logs = [];
        renderLogs();
    }


    function getStats() {
        const stats = {
            total: logs.length,
            byType: {},
            byLevel: {},
            byCategory: {}
        };
        
        logs.forEach(log => {
            stats.byType[log.type] = (stats.byType[log.type] || 0) + 1;
            if (log.type === 'log') {
                stats.byLevel[log.level] = (stats.byLevel[log.level] || 0) + 1;
                stats.byCategory[log.category] = (stats.byCategory[log.category] || 0) + 1;
            }
        });
        
        return stats;
    }

    // Инициализация при загрузке
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Экспорт API
    window.DebugPanel = Object.freeze({
        init,
        addLog,
        clearLogs,
        getStats,
        togglePanel
    });

})();
