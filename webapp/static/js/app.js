// Точка входа: переходы между экранами, нижнее меню, сообщения и обработка ошибок.
// Всё состояние живёт внутри createApp(), глобальных переменных нет.
import { createApi } from './api.js';
import { button, el } from './dom.js';
import { icon } from './icons.js';
import { card, catalog, help, list, my } from './screens.js';
import { initTelegram } from './telegram.js';
import { post } from './wizard.js';

const SCREENS = { catalog, list, card, post, my, help };

const TABS = [
  { name: 'catalog', label: 'Каталог', iconName: 'catalog' },
  { name: 'post', label: 'Разместить', iconName: 'plus' },
  { name: 'my', label: 'Мои', iconName: 'list' },
  { name: 'help', label: 'Помощь', iconName: 'help' },
];

// Какая вкладка подсвечена на каждом экране
const TAB_OF = { catalog: 'catalog', list: 'catalog', card: 'catalog', post: 'post', my: 'my', help: 'help' };

const TOAST_MS = 4000;

function errorScreen(error, retry) {
  return el(
    'div',
    { class: 'empty stack', role: 'alert' },
    el('h2', { text: 'Не получилось загрузить' }),
    el('p', { class: 'muted', text: error.message }),
    button({ label: 'Повторить', variant: 'secondary', onclick: retry }),
  );
}

function createApp() {
  const telegram = initTelegram();
  const api = createApi(() => telegram.initData);
  const ui = {
    header: document.getElementById('header'),
    screen: document.getElementById('screen'),
    tabbar: document.getElementById('tabbar'),
    toast: document.getElementById('toast'),
  };
  const state = {}; // общие данные между экранами, например черновик объявления
  const stack = [{ name: 'catalog', params: {} }];
  let renderId = 0;
  let toastTimer = 0;

  function toast(message) {
    ui.toast.textContent = message;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      ui.toast.textContent = '';
    }, TOAST_MS);
  }

  function navigate(name, params = {}) {
    stack.push({ name, params });
    render();
  }

  function back() {
    if (stack.length > 1) stack.pop();
    render();
  }

  function switchTab(name) {
    stack.length = 0;
    stack.push({ name, params: {} });
    render();
  }

  function updateChrome(screenName) {
    const canGoBack = stack.length > 1;
    const backButton = button({ label: 'Назад', iconName: 'back', variant: 'ghost', onclick: back });
    ui.header.replaceChildren(...(canGoBack ? [backButton] : []));
    telegram.setBackVisible(canGoBack);
    for (const tab of ui.tabbar.children) {
      if (tab.dataset.tab === TAB_OF[screenName]) tab.setAttribute('aria-current', 'page');
      else tab.removeAttribute('aria-current');
    }
  }

  function makeContext(params) {
    return { api, params, state, navigate, switchTab, toast, confirm: telegram.confirm, openChat: telegram.openChat };
  }

  async function render() {
    const id = ++renderId;
    const { name, params } = stack[stack.length - 1];
    updateChrome(name);
    ui.toast.textContent = ''; // сообщение относилось к прошлому экрану
    ui.screen.replaceChildren(el('p', { class: 'loading', text: 'Загрузка…' }));
    window.scrollTo(0, 0);

    let content;
    try {
      content = await SCREENS[name](makeContext(params));
    } catch (error) {
      content = errorScreen(error, render);
    }
    if (id !== renderId) return; // за это время открыли другой экран
    ui.screen.replaceChildren(content);
    ui.screen.querySelector('h1')?.focus({ preventScroll: true });
  }

  function buildTabs() {
    const tabs = TABS.map((tab) =>
      el(
        'button',
        { class: 'tab', type: 'button', 'data-tab': tab.name, onclick: () => switchTab(tab.name) },
        icon(tab.iconName),
        el('span', { text: tab.label }),
      ),
    );
    ui.tabbar.replaceChildren(...tabs);
  }

  buildTabs();
  telegram.onBack(back);
  render();
}

createApp();
