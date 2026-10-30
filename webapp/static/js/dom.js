// Построение страницы. Любой текст попадает в неё только через textContent
// или текстовые узлы, поэтому разметку из объявлений вставить нельзя.
import { icon } from './icons.js';

function applyProp(node, name, value) {
  if (value == null || value === false) return;
  if (name === 'class') node.className = value;
  else if (name === 'text') node.textContent = value;
  else if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
  else node.setAttribute(name, value === true ? '' : String(value));
}

export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) applyProp(node, name, value);
  node.append(...children.flat().filter((child) => child != null && child !== false));
  return node;
}

// Заголовок экрана; на него переводится фокус при смене экрана (для чтения вслух)
export function heading(text) {
  return el('h1', { tabindex: '-1', text });
}

export function button({ label, iconName, variant = 'primary', ...props }) {
  return el(
    'button',
    { class: `button button-${variant}`, type: 'button', ...props },
    iconName ? icon(iconName) : null,
    el('span', { text: label }),
  );
}

// Блокирует кнопку на время действия: двойное нажатие не отправит запрос дважды
export async function runBusy(target, task) {
  target.disabled = true;
  target.setAttribute('aria-busy', 'true');
  try {
    return await task();
  } finally {
    target.disabled = false;
    target.removeAttribute('aria-busy');
  }
}
