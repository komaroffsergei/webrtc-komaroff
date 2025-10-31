/**
 * Chat UI - управление отображением сообщений в чате
 */

(function() {
    'use strict';

    let messageLogElement = null;

    function init(messageLogEl) {
        messageLogElement = messageLogEl;
    }

    function addMessage(text, type = 'server', uid = null) {
        if (!messageLogElement) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}-message`;
        messageDiv.textContent = text;
        
        if (uid) {
            messageDiv.setAttribute('data-uid', uid);
        }
        
        messageLogElement.appendChild(messageDiv);
        scrollToBottom();
    }

    function addServerMessage(text, uid) {
        addMessage(text, 'server', uid);
    }

    function addUserMessage(text, uid) {
        addMessage(text, 'user', uid);
    }

    function addStatusMessage(text) {
        addMessage(text, 'status');
    }

    function scrollToBottom() {
        if (!messageLogElement) return;
        
        // Автоскролл только если чат развернут
        const chatWindow = document.querySelector('.chat-window');
        if (chatWindow && chatWindow.classList.contains('expanded')) {
            setTimeout(() => {
                messageLogElement.scrollTop = messageLogElement.scrollHeight;
            }, 100);
        }
    }

    function clearMessages() {
        if (!messageLogElement) return;
        messageLogElement.innerHTML = '';
    }

    // Экспорт API
    window.ChatUI = Object.freeze({
        init,
        addMessage,
        addServerMessage,
        addUserMessage,
        addStatusMessage,
        scrollToBottom,
        clearMessages
    });

})();
