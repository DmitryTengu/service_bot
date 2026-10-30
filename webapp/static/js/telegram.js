// Обёртка над Telegram.WebApp. Вне Telegram (в обычном браузере) работают запасные варианты,
// но запросы к серверу без подписи Telegram всё равно будут отклонены.

function readColor(variable) {
  return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
}

function paintTelegramChrome(webApp) {
  // Цвета берём из CSS-переменной, чтобы не дублировать их в скрипте
  const color = readColor('--color-bg');
  for (const method of ['setHeaderColor', 'setBackgroundColor', 'setBottomBarColor']) {
    try {
      webApp[method]?.(color);
    } catch {
      // Старые версии Telegram не знают часть методов; внешний вид от этого не страдает
    }
  }
}

export function initTelegram() {
  const webApp = window.Telegram?.WebApp;
  if (webApp) {
    webApp.ready();
    webApp.expand();
    paintTelegramChrome(webApp);
  }

  return {
    initData: webApp?.initData ?? '',

    openChat(url) {
      if (webApp?.openTelegramLink) webApp.openTelegramLink(url);
      else window.open(url, '_blank', 'noopener');
    },

    confirm(message) {
      if (webApp?.showConfirm) {
        return new Promise((resolve) => webApp.showConfirm(message, resolve));
      }
      return Promise.resolve(window.confirm(message));
    },

    // Кнопка «назад» в шапке Telegram; обработчик ставится один раз
    onBack(handler) {
      webApp?.BackButton?.onClick(handler);
    },

    setBackVisible(visible) {
      const backButton = webApp?.BackButton;
      if (!backButton) return;
      if (visible) backButton.show();
      else backButton.hide();
    },
  };
}
