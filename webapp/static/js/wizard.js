// Экран «Разместить»: пять шагов, предпросмотр и отправка. Один вопрос на шаг.
import { button, el, heading, runBusy } from './dom.js';
import { icon } from './icons.js';

// Те же границы, что в bot/validators.py. Сервер проверяет их заново; здесь они нужны,
// чтобы подсказать об ошибке сразу, а не после отправки.
const LIMITS = {
  title: { min: 3, max: 80 },
  description: { min: 10, max: 300 },
  price: { min: 1, max: 40 },
  location: { min: 2, max: 60 },
};

const FIELD_STEPS = [
  { key: 'title', label: 'Название', question: 'Как называется услуга?', hint: 'Например: Ремонт ноутбуков', multiline: false },
  { key: 'description', label: 'Описание', question: 'Опишите услугу коротко', hint: 'Что вы делаете и чем можете помочь.', multiline: true },
  { key: 'price', label: 'Цена', question: 'Сколько это стоит?', hint: 'Например: от 20 BYN или договорная', multiline: false },
  { key: 'location', label: 'Район или город', question: 'В каком районе или городе?', hint: 'Например: Минск, Уручье', multiline: false },
];

// Шаги: 0 категория, 1-4 текстовые поля, 5 предпросмотр
const TOTAL_STEPS = FIELD_STEPS.length + 1;
const PREVIEW_STEP = TOTAL_STEPS;

const emptyDraft = () => ({ step: 0, category: '', title: '', description: '', price: '', location: '' });

const normalize = (text) => text.trim().replace(/\s+/g, ' ');

function fieldError(key, raw) {
  const value = normalize(raw);
  const { min, max } = LIMITS[key];
  if (!value) return 'Заполните это поле.';
  if (value.length < min || value.length > max) {
    return `Нужно от ${min} до ${max} символов, сейчас ${value.length}.`;
  }
  return '';
}

function progress(position, text) {
  const fill = el('div', { class: 'progress-fill' });
  fill.style.width = `${Math.round((position / TOTAL_STEPS) * 100)}%`;
  const track = el('div', {
    class: 'progress-track',
    role: 'progressbar',
    'aria-label': text,
    'aria-valuemin': '0',
    'aria-valuemax': String(TOTAL_STEPS),
    'aria-valuenow': String(position),
  }, fill);
  return el('div', { class: 'progress' }, el('p', { class: 'muted', text }), track);
}

function navigation(back, next) {
  return el('div', { class: 'button-row' }, back, next);
}

const backButton = (onclick) => button({ label: 'Назад', iconName: 'back', variant: 'secondary', onclick });

function categoryStep(wizard) {
  const { draft, categories } = wizard;
  const error = el('p', { class: 'error', role: 'alert' });
  const choices = categories.map((category) =>
    el('button', { class: 'choice', type: 'button', 'aria-pressed': String(draft.category === category.key) }, icon(category.key), el('span', { text: category.title })),
  );
  choices.forEach((choice, index) => {
    choice.addEventListener('click', () => {
      draft.category = categories[index].key;
      error.textContent = '';
      choices.forEach((other) => other.setAttribute('aria-pressed', String(other === choice)));
    });
  });

  const next = button({
    label: 'Далее',
    onclick: () => {
      if (!draft.category) error.textContent = 'Выберите категорию.';
      else wizard.go(1);
    },
  });
  return [
    heading('Какая категория?'),
    progress(1, `Шаг 1 из ${TOTAL_STEPS}`),
    el('div', { class: 'choices' }, choices),
    error,
    navigation(backButton(() => wizard.ctx.switchTab('catalog')), next),
  ];
}

function textStep(wizard, step) {
  const { draft } = wizard;
  const { max } = LIMITS[step.key];
  const inputId = `field-${step.key}`;
  const input = el(step.multiline ? 'textarea' : 'input', {
    class: 'input',
    id: inputId,
    name: step.key,
    maxlength: String(max),
    autocomplete: 'off',
    enterkeyhint: 'next',
    'aria-describedby': `${inputId}-hint ${inputId}-error`,
  });
  input.value = draft[step.key];
  const counter = el('p', { class: 'muted' });
  const error = el('p', { class: 'error', role: 'alert', id: `${inputId}-error` });
  const updateCounter = () => {
    counter.textContent = `${normalize(input.value).length} из ${max}`;
  };
  input.addEventListener('input', updateCounter);
  updateCounter();

  const next = button({ label: 'Далее', type: 'submit' });
  const goBack = backButton(() => {
    draft[step.key] = input.value;
    wizard.go(draft.step - 1);
  });

  const form = el(
    'form',
    { class: 'stack', novalidate: true },
    el('div', { class: 'field' }, el('label', { for: inputId, class: 'muted', text: step.label }), input, counter, error),
    navigation(goBack, next),
  );
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    draft[step.key] = input.value;
    const problem = fieldError(step.key, input.value);
    input.setAttribute('aria-invalid', String(Boolean(problem)));
    error.textContent = problem;
    if (problem) input.focus();
    else wizard.go(draft.step + 1);
  });

  return [
    heading(step.question),
    progress(draft.step + 1, `Шаг ${draft.step + 1} из ${TOTAL_STEPS}`),
    el('p', { class: 'muted', id: `${inputId}-hint`, text: step.hint }),
    form,
  ];
}

function previewCard(draft, category) {
  return el(
    'div',
    { class: 'card' },
    el('h2', { class: 'card-title', text: draft.title }),
    el('p', { class: 'card-price', text: draft.price }),
    el('p', { class: 'card-text', text: normalize(draft.description) }),
    el('p', { class: 'card-meta' }, icon('pin'), el('span', { text: draft.location })),
    el('p', { class: 'card-meta' }, icon('catalog'), el('span', { text: category?.title ?? '' })),
  );
}

async function submit(wizard, error) {
  const { draft, ctx } = wizard;
  error.textContent = '';
  try {
    wizard.created = await ctx.api.createListing({
      category: draft.category,
      title: normalize(draft.title),
      description: normalize(draft.description),
      price: normalize(draft.price),
      location: normalize(draft.location),
    });
  } catch (problem) {
    error.textContent = problem.message;
    return;
  }
  ctx.state.draft = emptyDraft(); // черновик больше не нужен
  wizard.show();
}

function previewStep(wizard) {
  const { draft, categories } = wizard;
  const category = categories.find((item) => item.key === draft.category);
  const error = el('p', { class: 'error', role: 'alert' });
  const publish = button({
    label: 'Опубликовать',
    iconName: 'check',
    onclick: () => runBusy(publish, () => submit(wizard, error)),
  });
  return [
    heading('Проверьте объявление'),
    progress(TOTAL_STEPS, 'Последний шаг'),
    previewCard(draft, category),
    el('p', { class: 'muted', text: 'После публикации ваше имя и @username увидят все, кто откроет объявление.' }),
    error,
    navigation(backButton(() => wizard.go(TOTAL_STEPS - 1)), publish),
  ];
}

function doneStep(wizard) {
  const { ctx, created } = wizard;
  const text =
    created.status === 'active'
      ? 'Объявление опубликовано.'
      : 'Объявление отправлено на проверку. Пока оно проверяется, его видно только вам во вкладке «Мои».';
  return [
    heading('Готово'),
    el('div', { class: 'empty stack' }, icon('check'), el('p', { text })),
    button({ label: 'Мои объявления', iconName: 'list', onclick: () => ctx.switchTab('my') }),
    button({ label: 'В каталог', iconName: 'catalog', variant: 'secondary', onclick: () => ctx.switchTab('catalog') }),
  ];
}

function renderStep(wizard) {
  if (wizard.created) return doneStep(wizard);
  const { step } = wizard.draft;
  if (step === 0) return categoryStep(wizard);
  if (step === PREVIEW_STEP) return previewStep(wizard);
  return textStep(wizard, FIELD_STEPS[step - 1]);
}

export async function post(ctx) {
  // Черновик хранится в ctx.state: можно уйти на другую вкладку и вернуться
  ctx.state.draft ??= emptyDraft();
  ctx.state.categories ??= await ctx.api.categories();
  const root = el('section', { class: 'stack' });
  const wizard = {
    ctx,
    draft: ctx.state.draft,
    categories: ctx.state.categories,
    created: null,
    show() {
      root.replaceChildren(...renderStep(wizard));
      root.querySelector('h1')?.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    },
    go(step) {
      wizard.draft.step = step;
      wizard.show();
    },
  };
  wizard.show();
  return root;
}
