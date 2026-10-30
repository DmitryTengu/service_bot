// Экраны: каталог, список, карточка, «Мои объявления» и помощь.
// Каждый экран получает ctx (api, params, navigate, toast, ...) и возвращает готовый узел.
import { button, el, heading, runBusy } from './dom.js';
import { icon } from './icons.js';

// Как MAX_QUERY_LENGTH в webapp/api.py; сервер проверяет длину и сам
const SEARCH_MAX_LENGTH = 60;

const STATUS_VIEW = {
  pending: { icon: 'clock', label: 'На проверке', style: '' },
  active: { icon: 'check', label: 'Опубликовано', style: 'badge-active' },
  hidden: { icon: 'eyeOff', label: 'Скрыто', style: '' },
  rejected: { icon: 'xCircle', label: 'Отклонено', style: 'badge-rejected' },
};

const HELP_SECTIONS = [
  ['Как найти услугу', 'Откройте «Каталог», выберите категорию или введите слово в строке поиска. Нажмите на объявление, чтобы увидеть подробности.'],
  ['Как связаться с автором', 'В карточке нажмите «Написать автору»: откроется чат в Telegram. Если у автора нет @username, написать ему отсюда нельзя.'],
  ['Как разместить объявление', 'Откройте «Разместить» и ответьте на пять вопросов. Перед отправкой вы увидите, как будет выглядеть объявление. Ваше имя и @username увидят все, кто откроет объявление.'],
  ['Проверка объявлений', 'Новое объявление сначала проверяет администратор. Пока идёт проверка, его видно только вам во вкладке «Мои».'],
  ['Лимит объявлений', 'Число объявлений у одного человека ограничено. Ненужное можно скрыть или удалить во вкладке «Мои».'],
  ['Жалобы', 'Если объявление нарушает правила, нажмите «Пожаловаться» в его карточке.'],
];

function metaLine(iconName, text) {
  return el('p', { class: 'card-meta' }, icon(iconName), el('span', { text }));
}

function emptyState(title, text, action = null) {
  return el(
    'div',
    { class: 'empty stack' },
    el('h2', { text: title }),
    el('p', { class: 'muted', text }),
    action,
  );
}

function authorLabel(listing) {
  const name = listing.author_name || 'Без имени';
  return listing.author_username ? `${name} (@${listing.author_username})` : name;
}

// Выполняет действие и показывает ошибку сообщением, а не ломает экран
async function attempt(ctx, task) {
  try {
    await task();
  } catch (error) {
    ctx.toast(error.message);
  }
}

// ---------- каталог ----------

function searchForm(ctx) {
  const input = el('input', {
    class: 'input',
    id: 'search-input',
    type: 'search',
    name: 'q',
    maxlength: SEARCH_MAX_LENGTH,
    placeholder: 'Что вы ищете?',
    autocomplete: 'off',
    enterkeyhint: 'search',
  });
  const label = el('label', { class: 'visually-hidden', for: 'search-input', text: 'Поиск по каталогу' });
  const submit = button({ label: 'Найти', iconName: 'search', type: 'submit' });
  const form = el('form', { class: 'search', role: 'search' }, label, input, submit);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const q = input.value.trim();
    if (q) ctx.navigate('list', { q, title: `Поиск: ${q}` });
  });
  return form;
}

function categoryTile(ctx, category) {
  const open = () => ctx.navigate('list', { category: category.key, title: category.title });
  return el('button', { class: 'tile', type: 'button', onclick: open }, icon(category.key), el('span', { text: category.title }));
}

export async function catalog(ctx) {
  const categories = await ctx.api.categories();
  const showAll = () => ctx.navigate('list', { title: 'Все объявления' });
  return el(
    'section',
    { class: 'stack' },
    heading('Каталог'),
    searchForm(ctx),
    button({ label: 'Все объявления', iconName: 'list', variant: 'secondary', onclick: showAll }),
    el('div', { class: 'tiles' }, categories.map((category) => categoryTile(ctx, category))),
  );
}

// ---------- список ----------

function listingCard(ctx, listing) {
  const open = () => ctx.navigate('card', { id: listing.id });
  return el(
    'button',
    { class: 'card card-button', type: 'button', onclick: open },
    el('span', { class: 'card-title', text: listing.title }),
    el('span', { class: 'card-price', text: listing.price }),
    el('span', { class: 'card-text', text: listing.description }),
    el('span', { class: 'card-meta' }, icon('pin'), el('span', { text: listing.location })),
  );
}

export async function list(ctx) {
  const { category, q, title = 'Объявления' } = ctx.params;
  const summary = el('p', { class: 'muted' });
  const items = el('div', { class: 'stack' });
  const more = button({ label: 'Показать ещё', variant: 'secondary', onclick: () => runBusy(more, loadNext) });
  let page = 0;

  async function showPage() {
    const data = await ctx.api.listings({ category, q, page });
    items.append(...data.items.map((listing) => listingCard(ctx, listing)));
    summary.textContent = `Найдено: ${data.total}`;
    more.hidden = page + 1 >= data.pages;
    return data.total;
  }

  async function loadNext() {
    page += 1;
    try {
      await showPage();
    } catch (error) {
      page -= 1; // не вышло: следующее нажатие повторит ту же страницу
      ctx.toast(error.message);
    }
  }

  if ((await showPage()) === 0) {
    return el('section', { class: 'stack' }, heading(title), emptyState('Ничего не найдено', 'Попробуйте другое слово или другую категорию.'));
  }
  return el('section', { class: 'stack' }, heading(title), summary, items, more);
}

// ---------- карточка ----------

function listingDetails(listing) {
  return el(
    'div',
    { class: 'card' },
    el('p', { class: 'card-price', text: listing.price }),
    el('p', { class: 'card-text', text: listing.description }),
    metaLine('pin', listing.location),
    listing.phone ? metaLine('phone', listing.phone) : null,
    metaLine('user', authorLabel(listing)),
    metaLine('catalog', listing.category_title),
  );
}

function contactBlock(ctx, listing) {
  if (!listing.contact_url) {
    return el('p', { class: 'muted', text: 'У автора нет @username, написать ему отсюда нельзя.' });
  }
  return button({ label: 'Написать автору', iconName: 'send', onclick: () => ctx.openChat(listing.contact_url) });
}

async function sendReport(ctx, listing) {
  if (!(await ctx.confirm('Отправить жалобу на это объявление администраторам?'))) return;
  await attempt(ctx, async () => {
    await ctx.api.report(listing.id);
    ctx.toast('Жалоба отправлена.');
  });
}

export async function card(ctx) {
  const listing = await ctx.api.listing(ctx.params.id);
  const report = button({
    label: 'Пожаловаться',
    iconName: 'flag',
    variant: 'danger',
    onclick: () => runBusy(report, () => sendReport(ctx, listing)),
  });
  return el('article', { class: 'stack' }, heading(listing.title), listingDetails(listing), contactBlock(ctx, listing), report);
}

// ---------- мои объявления ----------

function myCard(item, actions) {
  const view = STATUS_VIEW[item.status] ?? STATUS_VIEW.pending;
  const toggle = toggleButton(item, actions);
  const remove = button({ label: 'Удалить', iconName: 'trash', variant: 'danger', onclick: () => actions.remove(item) });
  return el(
    'article',
    { class: 'card' },
    el('span', { class: `badge ${view.style}` }, icon(view.icon), el('span', { text: view.label })),
    el('h2', { class: 'card-title', text: item.title }),
    el('p', { class: 'card-price', text: item.price }),
    metaLine('pin', item.location),
    // Кнопки друг под другом: две в ряд на узком экране ломали бы слова
    el('div', { class: 'stack' }, toggle, remove),
  );
}

// Скрыть можно опубликованное, показать только скрытое; в остальных случаях кнопки нет
function toggleButton(item, actions) {
  if (item.status === 'active') {
    return button({ label: 'Скрыть', iconName: 'eyeOff', variant: 'secondary', onclick: () => actions.toggle(item) });
  }
  if (item.status === 'hidden') {
    return button({ label: 'Показать', iconName: 'eye', variant: 'secondary', onclick: () => actions.toggle(item) });
  }
  return null;
}

export async function my(ctx) {
  const items = await ctx.api.myListings();
  const container = el('div', { class: 'stack' });

  const emptyMine = () =>
    emptyState(
      'У вас пока нет объявлений',
      'Разместите первое, это займёт пару минут.',
      button({ label: 'Разместить', iconName: 'plus', onclick: () => ctx.switchTab('post') }),
    );

  const redraw = () => {
    const cards = items.map((item) => myCard(item, actions));
    container.replaceChildren(...(cards.length ? cards : [emptyMine()]));
  };

  const actions = {
    toggle: (item) =>
      attempt(ctx, async () => {
        const changed = item.status === 'active' ? await ctx.api.hide(item.id) : await ctx.api.show(item.id);
        items[items.indexOf(item)] = changed;
        redraw();
      }),
    remove: async (item) => {
      if (!(await ctx.confirm('Удалить это объявление? Отменить нельзя.'))) return;
      await attempt(ctx, async () => {
        await ctx.api.remove(item.id);
        items.splice(items.indexOf(item), 1);
        redraw();
      });
    },
  };

  redraw();
  return el('section', { class: 'stack' }, heading('Мои объявления'), container);
}

// ---------- помощь ----------

export async function help() {
  const sections = HELP_SECTIONS.map(([title, text]) =>
    el('div', { class: 'card' }, el('h2', { text: title }), el('p', { text })),
  );
  return el('section', { class: 'stack' }, heading('Помощь'), sections);
}
