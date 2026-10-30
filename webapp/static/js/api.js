// Обращения к серверу. Подпись Telegram уходит в заголовке Authorization: tma <initData>.
// Номер пользователя серверу не передаётся: он берёт его только из проверенной подписи.

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

const GENERIC_ERROR = 'Что-то пошло не так. Попробуйте ещё раз.';
const NETWORK_ERROR = 'Нет связи с сервером. Проверьте интернет.';

export function createApi(getInitData) {
  async function request(method, path, body) {
    const headers = { Authorization: `tma ${getInitData()}` };
    if (body !== undefined) headers['Content-Type'] = 'application/json';

    let response;
    try {
      const payload = body === undefined ? undefined : JSON.stringify(body);
      response = await fetch(path, { method, headers, body: payload });
    } catch {
      throw new ApiError(0, NETWORK_ERROR);
    }
    if (response.status === 204) return null;

    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new ApiError(response.status, data.detail || GENERIC_ERROR);
    return data;
  }

  return {
    categories: () => request('GET', '/api/categories'),

    listings({ category, q, page = 0 }) {
      const params = new URLSearchParams({ page: String(page) });
      if (category) params.set('category', category);
      if (q) params.set('q', q);
      return request('GET', `/api/listings?${params}`);
    },

    listing: (id) => request('GET', `/api/listings/${id}`),
    createListing: (fields) => request('POST', '/api/listings', fields),
    report: (id) => request('POST', `/api/listings/${id}/report`),

    myListings: () => request('GET', '/api/my/listings'),
    hide: (id) => request('POST', `/api/my/listings/${id}/hide`),
    show: (id) => request('POST', `/api/my/listings/${id}/show`),
    remove: (id) => request('DELETE', `/api/my/listings/${id}`),
  };
}
