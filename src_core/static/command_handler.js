/**
 * Command Handler - центральный обработчик команд от сервера и клиента
 * 
 * Архитектура:
 * - Регистрация обработчиков команд через register()
 * - Динамическая маршрутизация по method
 * - Логирование выполнения команд
 * - Обработка ошибок с fallback
 */

(function() {
    'use strict';

    const handlers = new Map();
    const LOG_SERVICE = 'command';

    function log(type, message) {
        if (typeof window.logEvent === 'function') {
            window.logEvent({service: LOG_SERVICE, type, message});
        }
    }

    /**
     * Регистрация обработчика команды
     * @param {string} method - имя метода команды
     * @param {Function} handler - функция обработчик (params, uid) => void
     */
    function register(method, handler) {
        if (typeof handler !== 'function') {
            log('error', `[CommandHandler] Handler for "${method}" must be a function`);
            return;
        }
        handlers.set(method, handler);
        log('info', `[CommandHandler] Registered handler for "${method}"`);
    }

    /**
     * Выполнение команды
     * @param {string} method - имя метода
     * @param {*} params - параметры команды
     * @param {string} uid - уникальный идентификатор команды
     */
    async function execute(method, params, uid) {
        const handler = handlers.get(method);
        
        if (!handler) {
            log('warn', `[CommandHandler] No handler registered for method "${method}"`);
            return;
        }

        try {
            log('info', `[CommandHandler] Executing "${method}" with uid=${uid}`);
            await handler(params, uid);
        } catch (error) {
            log('error', `[CommandHandler] Error executing "${method}": ${error?.message || error}`);
        }
    }

    /**
     * Обработка входящего сообщения от сервера через SSE
     * @param {Object} message - объект сообщения
     */
    function handleServerMessage(message) {
        if (!message || typeof message !== 'object') {
            return;
        }

        if (typeof window.logEvent === 'function' && window.logEvent(message)) {
            return;
        }

        const { type, descr, method, params, uid, text } = message;

        switch (type) {
            case 'command':
                if (method) {
                    execute(method, params, uid);
                }
                break;

            case 'message':
                if (descr === 'send' && text) {
                    // Сообщение от сервера - отображаем в чате
                    if (window.ChatUI && window.ChatUI.addServerMessage) {
                        window.ChatUI.addServerMessage(text, uid);
                    }
                }
                break;

            case 'warning':
                if (descr && window.WarningUI) {
                    window.WarningUI.showWarning(descr, uid);
                }
                break;

            default:
                log('debug', `[CommandHandler] Unhandled message type: ${type}`);
        }
    }

    /**
     * Отправка сообщения на сервер
     * @param {string} text - текст сообщения
     * @returns {Promise<Object>} - ответ сервера
     */
    async function sendMessage(text) {
        try {
            const response = await fetch('/message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
            });

            if (!response.ok) {
                throw new Error(`Server responded with ${response.status}`);
            }

            const data = await response.json();
            log('info', `[CommandHandler] Message sent, uid=${data.uid}`);
            return data;
        } catch (error) {
            log('error', `[CommandHandler] Failed to send message: ${error?.message || error}`);
            throw error;
        }
    }

    // Регистрация базовых команд

    // alert - показать alert
    register('alert', (params) => {
        const msg = typeof params === 'object' ? params.msg : params;
        alert(msg || 'Alert from server');
    });

    // console - вывод в консоль
    register('console', (params) => {
        log('info', `[Server Command] ${JSON.stringify(params)}`);
    });

    // reload - перезагрузка страницы
    register('reload', () => {
        window.location.reload();
    });

    // redirect - редирект на URL
    register('redirect', (params) => {
        const url = typeof params === 'object' ? params.url : params;
        if (url) {
            window.location.href = url;
        }
    });

    // eval_js - выполнение JS кода (использовать осторожно!)
    register('eval_js', (params) => {
        const code = typeof params === 'object' ? params.code : params;
        if (code) {
            try {
                eval(code);
            } catch (e) {
                log('error', `[CommandHandler] eval_js error: ${e?.message || e}`);
            }
        }
    });

    // Экспорт API
    window.CommandHandler = Object.freeze({
        register,
        execute,
        handleServerMessage,
        sendMessage
    });

})();
