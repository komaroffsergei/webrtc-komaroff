(function () {
    const cfg = window.AppConfig;
    let isConnected = false;
    let pc = null;
    let sender = null;
    let micStream = null;
    let vadInstance = null;
    let backgroundViz = null;
    let micWaveformViz = null;
    let eventSource = null;

    let els = {};
    const DEFAULT_SERVICE = 'app-assistant';

    function log(type, message, service) {
        if (typeof window.logEvent === 'function') {
            window.logEvent({
                service: (service ? DEFAULT_SERVICE + '-' + service : DEFAULT_SERVICE),
                type,
                message
            });
        }
    }

    // Установка размеров canvas с запасом
    function setupCanvas() {
        if (!els.waveBackground || !els.chatWindow) return;

        const canvas = els.waveBackground;
        const container = els.chatWindow;
        const rect = container.getBoundingClientRect();

        // Устанавливаем размеры с запасом
        canvas.width = rect.width + 20; // Запас по ширине
        canvas.height = rect.height + 20; // Запас по высоте

        // Увеличиваем размеры для waveform в кнопке
        if (els.micWaveform) {
            els.micWaveform.width = 140;
            els.micWaveform.height = 40;
        }
    }

    function addMessage(text, type = 'server', uid = null) {
        if (window.ChatUI) {
            window.ChatUI.addMessage(text, type, uid);
        }
    }

    function updateStatus(text) {
        if (els.connectionStatus) {
            els.connectionStatus.textContent = text;
        }
    }

    function setupBackgroundWaveform(stream) {
        try {
            // Останавливаем предыдущую визуализацию
            if (backgroundViz) {
                backgroundViz.stop();
            }

            if (!els.waveBackground) return;

            const canvas = els.waveBackground;
            const ctx = canvas.getContext('2d');

            // Создаем временный конфиг для фоновой визуализации с увеличенными размерами
            const bgConfig = {
                ...cfg,
                audio: {
                    ...cfg.audio,
                    analyser: {
                        fftSize: 512,
                        historySeconds: 3
                    }
                },
                ui: {
                    canvas: {
                        width: canvas.width,
                        height: canvas.height
                    },
                    colors: {
                        grid: 'transparent',
                        in: '#007aff',
                        out: '#007aff'
                    }
                }
            };

            // Создаем кастомный drawer для фона с увеличенной амплитудой
            const drawer = createSensitiveWaveDrawer(ctx, bgConfig, 2.5);

            // Создаем AudioContext и подключаем визуализацию
            const ac = new (window.AudioContext || window.webkitAudioContext)();
            backgroundViz = window.AudioViz.attachAnalyserDraw(
                ac,
                stream,
                bgConfig,
                (hist) => drawer(hist, '#007aff')
            );

        } catch (e) {
            log('warn', `Background waveform failed: ${e?.message || e}`, 'viz');
        }
    }

    function setupMicWaveform(stream) {
        try {
            // Останавливаем предыдущую визуализацию
            if (micWaveformViz) {
                micWaveformViz.stop();
            }

            if (!els.micWaveform) return;

            const canvas = els.micWaveform;
            const ctx = canvas.getContext('2d');

            // Создаем конфиг для waveform в кнопке
            const micWaveformConfig = {
                ...cfg,
                ui: {
                    canvas: {
                        width: canvas.width,
                        height: canvas.height
                    },
                    colors: {
                        grid: 'transparent',
                        in: '#ffffff',
                        out: '#ffffff'
                    }
                },
                audio: {
                    ...cfg.audio,
                    analyser: {
                        fftSize: 256,
                        historySeconds: 0.5
                    }
                }
            };

            // Создаем кастомный drawer для кнопки с увеличенной амплитудой
            const drawer = createSensitiveWaveDrawer(ctx, micWaveformConfig, 3.0);

            // Создаем AudioContext и подключаем визуализацию
            const ac = new (window.AudioContext || window.webkitAudioContext)();
            micWaveformViz = window.AudioViz.attachAnalyserDraw(
                ac,
                stream,
                micWaveformConfig,
                (hist) => drawer(hist, '#ffffff')
            );

        } catch (e) {
            log('warn', `Mic waveform failed: ${e?.message || e}`, 'viz');
        }
    }

    // Создаем кастомный drawer с увеличенной чувствительностью
    function createSensitiveWaveDrawer(ctx2d, config, sensitivityMultiplier = 2.0) {
        const W = config.ui.canvas.width;
        const H = config.ui.canvas.height;
        const mid = H / 2;
        const amp = mid * sensitivityMultiplier;
        const gridColor = config.ui.colors.grid;

        return function draw(history, stroke) {
            ctx2d.clearRect(0, 0, W, H);

            // Рисуем центральную линию
            ctx2d.strokeStyle = gridColor;
            ctx2d.lineWidth = 1;
            ctx2d.beginPath();
            ctx2d.moveTo(0, mid);
            ctx2d.lineTo(W, mid);
            ctx2d.stroke();

            // Рисуем waveform с увеличенной амплитудой
            const step = Math.max(1, Math.floor(history.length / W));
            ctx2d.strokeStyle = stroke;
            ctx2d.lineWidth = 2;
            ctx2d.beginPath();

            for (let x = 0, i = 0; x < W; x++, i += step) {
                let lo = 1, hi = -1;
                const end = Math.min(i + step, history.length);
                for (let j = i; j < end; j++) {
                    const v = history[j];
                    const amplifiedV = Math.sign(v) * Math.pow(Math.abs(v), 0.7);
                    if (amplifiedV < lo) lo = amplifiedV;
                    if (amplifiedV > hi) hi = amplifiedV;
                }
                const y1 = mid + lo * amp;
                const y2 = mid + hi * amp;
                ctx2d.moveTo(x, y1);
                ctx2d.lineTo(x, y2);
            }
            ctx2d.stroke();
        };
    }

    function expandChatWindow() {
        if (els.chatWindow) {
            els.chatWindow.classList.add('expanded');
            // Обновляем размеры canvas после разворачивания с задержкой
            setTimeout(() => {
                setupCanvas();
            }, 100);
        }
        if (els.micButton) {
            els.micButton.classList.add('expanded');
        }
        // Прокручиваем к последнему сообщению после разворачивания
        setTimeout(() => {
            if (els.messageLog) {
                els.messageLog.scrollTop = els.messageLog.scrollHeight;
            }
        }, 300);
    }

    function collapseChatWindow() {
        if (els.chatWindow) {
            els.chatWindow.classList.remove('expanded');
        }
        if (els.micButton) {
            els.micButton.classList.remove('expanded');
        }
    }

    async function toggleConnection() {
        if (!isConnected) {
            await connect();
        } else {
            disconnect();
        }
    }

    async function connect() {
        try {
            updateStatus('Подключение...');
            addMessage('Подключение...', 'status');
            expandChatWindow();

            // Получаем настройки аудио из элементов управления
            const audioConstraints = getAudioConstraints();

            // Логируем настройки
            log(
                'info',
                `Requesting microphone: EC=${audioConstraints.echoCancellation}, NS=${audioConstraints.noiseSuppression}, SR=${audioConstraints.sampleRate}`,
                'audio'
            );

            // Получаем доступ к микрофону
            micStream = await navigator.mediaDevices.getUserMedia({
                audio: audioConstraints,
                video: false
            });

            // Даем время на обновление DOM перед настройкой waveform
            setTimeout(() => {
                // Настраиваем waveform на фоне
                setupBackgroundWaveform(micStream);

                // Настраиваем waveform в кнопке
                setupMicWaveform(micStream);
            }, 150);

            // Создаем PeerConnection
            pc = await window.WebRTC.createPeer(cfg);
            sender = pc.addTrack(micStream.getAudioTracks()[0], micStream);

            // Настраиваем обработчик входящих треков
            pc.ontrack = (event) => {
                const stream = event.streams[0] || new MediaStream([event.track]);
                if (els.remoteAudio) {
                    els.remoteAudio.srcObject = stream;
                }
                updateStatus('Подключено');
                addMessage('Соединение установлено', 'server');
            };

            // Начинаем negotiation
            await window.WebRTC.negotiate(pc, cfg);
            isConnected = true;

        } catch (e) {
            log('error', `Connection failed: ${e?.message || e}`, 'webrtc');
            updateStatus('Ошибка подключения');
            addMessage(`Ошибка: ${e.message}`, 'status');
            disconnect();
        }
    }

    function disconnect() {
        try {
            if (vadInstance) {
                vadInstance.cleanup();
                vadInstance = null;
            }
            if (pc) {
                pc.close();
                pc = null;
            }
            if (micStream) {
                micStream.getTracks().forEach(track => track.stop());
                micStream = null;
            }
            if (backgroundViz) {
                backgroundViz.stop();
                backgroundViz = null;
            }
            if (micWaveformViz) {
                micWaveformViz.stop();
                micWaveformViz = null;
            }

            isConnected = false;
            collapseChatWindow();
            updateStatus('Отключено');
            addMessage('Соединение разорвано', 'server');

            // Очищаем canvas
            if (els.waveBackground) {
                const ctx = els.waveBackground.getContext('2d');
                ctx.clearRect(0, 0, els.waveBackground.width, els.waveBackground.height);
            }

            if (els.micWaveform) {
                const micCtx = els.micWaveform.getContext('2d');
                micCtx.clearRect(0, 0, els.micWaveform.width, els.micWaveform.height);
            }

        } catch (e) {
            log('warn', `Disconnect error: ${e?.message || e}`, 'webrtc');
        }
    }

    // Обработка текстового ввода
    async function handleTextInput(e) {
        if (e.key === 'Enter' && e.target.value.trim()) {
            const text = e.target.value.trim();
            addMessage(text, 'user');
            e.target.value = '';

            // Отправляем сообщение на сервер
            try {
                await window.CommandHandler.sendMessage(text);
            } catch (error) {
                addMessage('Ошибка отправки сообщения', 'status');
            }
        }
    }

    // Инициализация SSE
    function initSSE() {
        try {
            if (eventSource) {
                eventSource.close();
            }

            eventSource = new EventSource('/events');

            eventSource.onmessage = (e) => {
                processMessage(e.data);
            };

            eventSource.onopen = () => {
                logEvent({
                    service: DEFAULT_SERVICE + '-sse',
                    type: 'info',
                    message: `SSE connected`
                });
                updateStatus('Подключено к серверу');
            };

            eventSource.onerror = (e) => {
                logEvent({
                    service: DEFAULT_SERVICE + '-sse',
                    type: 'info',
                    ;o
                });
                updateStatus('Переподключение...');
                setTimeout(() => {
                    initSSE();
                }, 3000);
            };

        } catch (e) {
            logEvent({
                service: DEFAULT_SERVICE + '-sse',
                type: 'error',
                message: `SSE failed: ${e?.message || e}`
            });

        }
    }

    // Инициализация элементов управления
    function initAudioControls() {
        const vadEnableEl = document.getElementById('vadEnable');
        const vadThreshEl = document.getElementById('vadThresh');
        const vadLevelEl = document.getElementById('vadLevel');
        const ecEnableEl = document.getElementById('ecEnable');
        const nsEnableEl = document.getElementById('nsEnable');

        // Обновление отображения порога VAD
        if (vadThreshEl && vadLevelEl) {
            vadThreshEl.addEventListener('input', (e) => {
                const value = e.target.value;
                vadLevelEl.textContent = `${value} dBFS`;
                log('info', `VAD threshold changed: ${value} dBFS`, 'audio');
            });
        }

        // Логирование включения/выключения VAD
        if (vadEnableEl) {
            vadEnableEl.addEventListener('change', (e) => {
                const enabled = e.target.checked;
                log('info', `VAD ${enabled ? 'enabled' : 'disabled'}`, 'audio');
                // Обновляем VAD если есть активный экземпляр
                if (vadInstance) {
                    vadInstance.enabled = enabled;
                }
            });
        }

        // Логирование echoCancellation
        if (ecEnableEl) {
            ecEnableEl.addEventListener('change', (e) => {
                const enabled = e.target.checked;
                log('info', `Echo Cancellation ${enabled ? 'enabled' : 'disabled'}`, 'audio');
            });
        }

        // Логирование noiseSuppression
        if (nsEnableEl) {
            nsEnableEl.addEventListener('change', (e) => {
                const enabled = e.target.checked;
                log('info', `Noise Suppression ${enabled ? 'enabled' : 'disabled'}`, 'audio');
            });
        }

        // Логируем начальное состояние
        log(
            'info',
            `Audio controls initialized: VAD=${vadEnableEl?.checked}, EC=${ecEnableEl?.checked}, NS=${nsEnableEl?.checked}, Threshold=${vadThreshEl?.value}dBFS`,
            'audio'
        );
    }

    // Получение настроек аудио для getUserMedia
    function getAudioConstraints() {
        const ecEnable = document.getElementById('ecEnable')?.checked ?? true;
        const nsEnable = document.getElementById('nsEnable')?.checked ?? true;

        return {
            echoCancellation: ecEnable,
            noiseSuppression: nsEnable,
            autoGainControl: true,
            sampleRate: 48000,
            channelCount: 1
        };
    }

    function setInteractiveControlsDisabled(disabled) {
        const root = els.assistantContainer || document;
        root.querySelectorAll('input').forEach(control => {
            if (control && 'disabled' in control) {
                control.disabled = disabled;
            }
        });
    }

    function processMessage(json) {
        let data
        try {
            data = JSON.parse(json);
            logEvent(data)
        } catch (err) {
            log('error', `SSE message parse error: ${err?.message || err}`, 'sse');
            return
        }

        if (data.name) {
            switch (data.name) {
                case 'model_downloading_status':
                    if (data.type === 'info') {
                        if (data.message === 'downloading') {
                            setInteractiveControlsDisabled(true);
                            updateStatus('Скачивание модели');
                        } else if (data.message === 'exists') {
                            setInteractiveControlsDisabled(false);
                            if (eventSource) {
                                updateStatus('Подключено');
                            } else {
                                initSSE();
                            }
                        }
                    } else if (data.type === 'error') {
                        if (data.message === 'exists') {
                            setInteractiveControlsDisabled(true);
                            updateStatus(`Ошибка получения модели: ${data.message}`);
                        }
                    }
                    break;
                case 'model_downloading_percent':
                       setInteractiveControlsDisabled(true);
                       updateStatus(`Скачивание модели ${data.message}%`);
                    break;
            }
        }

    }

    // Инициализация
    window.addEventListener('load', () => {
        // Инициализируем элементы после загрузки DOM
        els = {
            micButton: document.getElementById('micButton'),
            messageLog: document.getElementById('messageLog'),
            connectionStatus: document.getElementById('connectionStatus'),
            waveBackground: document.getElementById('waveBackground'),
            remoteAudio: document.getElementById('remoteAudio'),
            assistantContainer: document.getElementById('assistantContainer'),
            textInput: document.getElementById('textInput'),
            micWaveform: document.getElementById('micWaveform'),
            chatWindow: document.querySelector('.chat-window')
        };

        // Инициализируем ChatUI
        if (window.ChatUI && els.messageLog) {
            window.ChatUI.init(els.messageLog);
        }

        // Устанавливаем начальные размеры canvas с запасом
        if (els.waveBackground) {
            els.waveBackground.width = 420; // 400 + 20 запаса
            els.waveBackground.height = 540; // 520 + 20 запаса
        }

        if (els.micButton) {
            els.micButton.addEventListener('click', toggleConnection);
        }

        if (els.textInput) {
            els.textInput.addEventListener('keypress', handleTextInput);
        }

        // Инициализируем элементы управления аудио
        initAudioControls();

        // Инициализируем SSE
        initSSE();
    });

    window.addEventListener('resize', () => {
        if (els.chatWindow && els.chatWindow.classList.contains('expanded')) {
            setupCanvas();
            if (isConnected && micStream) {
                setTimeout(() => {
                    setupBackgroundWaveform(micStream);
                }, 100);
            }
        }
    });

})();
