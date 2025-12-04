// /**
//  * Warning UI - отображение предупреждений об уровне звука
//  */
//
// (function() {
//     'use strict';
//
//     const warnings = {
//         'mic_too_loud': 'Микрофон слишком громкий',
//         'mic_too_quiet': 'Микрофон слишком тихий',
//         'mic_too_noise': 'Обнаружен высокий уровень шума'
//     };
//
//     let warningContainer = null;
//     let currentWarning = null;
//     let hideTimer = null;
//
//     function init() {
//         // Создаем контейнер для предупреждений если его нет
//         if (!warningContainer) {
//             warningContainer = document.createElement('div');
//             warningContainer.id = 'warningContainer';
//             warningContainer.className = 'warning-container';
//             document.body.appendChild(warningContainer);
//         }
//     }
//
//     function showWarning(descr, uid = null) {
//         const text = warnings[descr] || descr;
//
//         // Очищаем предыдущий таймер
//         if (hideTimer) {
//             clearTimeout(hideTimer);
//             hideTimer = null;
//         }
//
//         // Если такое же предупреждение уже показано - не дублируем
//         if (currentWarning && currentWarning.textContent === text) {
//             resetHideTimer();
//             return;
//         }
//
//         // Создаем элемент предупреждения
//         const warningEl = document.createElement('div');
//         warningEl.className = 'warning-message';
//         warningEl.textContent = text;
//
//         if (uid) {
//             warningEl.setAttribute('data-uid', uid);
//         }
//
//         // Добавляем в контейнер
//         if (!warningContainer) {
//             init();
//         }
//
//         warningContainer.innerHTML = '';
//         warningContainer.appendChild(warningEl);
//         currentWarning = warningEl;
//
//         // Показываем с анимацией
//         setTimeout(() => {
//             warningEl.classList.add('visible');
//         }, 10);
//
//         resetHideTimer();
//     }
//
//     function resetHideTimer() {
//         if (hideTimer) {
//             clearTimeout(hideTimer);
//         }
//
//         // Автоматически скрываем через 5 секунд
//         hideTimer = setTimeout(() => {
//             hideWarning();
//         }, 5000);
//     }
//
//     function hideWarning() {
//         if (!currentWarning) return;
//
//         currentWarning.classList.remove('visible');
//
//         setTimeout(() => {
//             if (warningContainer) {
//                 warningContainer.innerHTML = '';
//             }
//             currentWarning = null;
//         }, 300);
//
//         if (hideTimer) {
//             clearTimeout(hideTimer);
//             hideTimer = null;
//         }
//     }
//
//     // Инициализация при загрузке
//     if (document.readyState === 'loading') {
//         document.addEventListener('DOMContentLoaded', init);
//     } else {
//         init();
//     }
//
//     // Экспорт API
//     window.WarningUI = Object.freeze({
//         init,
//         showWarning,
//         hideWarning
//     });
//
// })();
