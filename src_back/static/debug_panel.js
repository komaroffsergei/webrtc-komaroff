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
        'general': true
    };

    function init() {
        createDebugPanel();
        attachEventListeners();
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
        
        ['system', 'webrtc', 'nats', 'audio', 'general'].forEach(category => {
            const btn = document.createElement('button');
            btn.className = 'filter-btn filter-category active';
            btn.textContent = category;
            btn.dataset.category = category;
            btn.onclick = () => toggleCategoryFilter(category, btn);
            categoryFilters.appendChild(btn);
        });
        
        debugPanel.appendChild(categoryFilters);
        
        // Кнопка очистки
        const controls = document.createElement('div');
        controls.className = 'debug-controls';
        
        clearButton = document.createElement('button');
        clearButton.className = 'clear-btn';
        clearButton.textContent = 'Очистить';
        clearButton.onclick = clearLogs;
        controls.appendChild(clearButton);
        
        const exportButton = document.createElement('button');
        exportButton.className = 'export-btn';
        exportButton.textContent = 'Экспорт';
        exportButton.onclick = exportLogs;
        controls.appendChild(exportButton);
        
        debugPanel.appendChild(controls);
        
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
        const logEntry = {
            timestamp,
            type: event.type || 'unknown',
            level: event.level || 'info',
            category: event.category || 'general',
            uid: event.uid,
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
            
            let content = '';
            
            if (log.type === 'log') {
                content = `[${time}] [${log.level.toUpperCase()}] [${log.category}] ${log.data.message}`;
            } else if (log.type === 'command') {
                content = `[${time}] [COMMAND] ${log.data.method} ${JSON.stringify(log.data.params || {})}`;
            } else if (log.type === 'message') {
                content = `[${time}] [MESSAGE] [${log.data.descr}] ${log.data.text}`;
            } else if (log.type === 'warning') {
                content = `[${time}] [WARNING] ${log.data.descr}`;
            } else {
                content = `[${time}] ${JSON.stringify(log.data)}`;
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

    function exportLogs() {
        const dataStr = JSON.stringify(logs, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        
        const link = document.createElement('a');
        link.href = url;
        link.download = `sse-logs-${Date.now()}.json`;
        link.click();
        
        URL.revokeObjectURL(url);
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
        exportLogs,
        getStats,
        togglePanel
    });

})();
