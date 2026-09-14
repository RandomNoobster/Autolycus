/*
 * Autolycus service worker: shows beige reminder notifications delivered by browser push.
 *
 * Deliberately minimal: no fetch handler and no caching, so pages load exactly as they
 * would without a worker. Payloads use the Declarative Web Push shape:
 * { web_push: 8030, notification: { title, body, navigate, tag, timestamp, requireInteraction }, autolycus: { kind, nationId } }
 */

const FALLBACK_TITLE = 'Autolycus reminder';
const FALLBACK_PATH = '/reminders';

self.addEventListener('install', (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

function readPayload(data) {
  if (!data) return {};
  try {
    const parsed = data.json();
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch (err) {
    try {
      const text = data.text();
      return text ? { notification: { body: text } } : {};
    } catch (err2) {
      return {};
    }
  }
}

/** Resolve where a click should go. Only http(s) URLs are opened. */
function resolveUrl(raw) {
  try {
    const url = new URL(typeof raw === 'string' && raw ? raw : FALLBACK_PATH, self.location.origin);
    if (url.protocol === 'https:' || url.protocol === 'http:') return url.href;
  } catch (err) {
    // Fall back to the reminders page below.
  }
  return new URL(FALLBACK_PATH, self.location.origin).href;
}

self.addEventListener('push', (event) => {
  const payload = readPayload(event.data);
  const notification =
    payload.notification && typeof payload.notification === 'object' ? payload.notification : {};
  const title =
    typeof notification.title === 'string' && notification.title.trim()
      ? notification.title
      : FALLBACK_TITLE;
  const body = typeof notification.body === 'string' ? notification.body : '';
  const url = resolveUrl(notification.navigate);
  const tag = typeof notification.tag === 'string' && notification.tag ? notification.tag : undefined;

  const options = {
    body,
    icon: '/assets/icon.png',
    data: { url },
    requireInteraction: notification.requireInteraction === true,
  };
  if (tag) {
    options.tag = tag;
    // A later reminder for the same nation replaces the earlier one; alert again instead of updating silently.
    options.renotify = true;
  }
  if (typeof notification.timestamp === 'number' && Number.isFinite(notification.timestamp)) {
    options.timestamp = notification.timestamp;
  }

  // Every push must show a notification, so retry with minimal options if the full set is rejected.
  event.waitUntil(
    self.registration
      .showNotification(title, options)
      .catch(() => self.registration.showNotification(title, { body, data: { url } }))
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = resolveUrl(event.notification.data && event.notification.data.url);

  event.waitUntil(
    (async () => {
      const target = new URL(url);
      if (target.origin === self.location.origin) {
        const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        const existing = windows.find((client) => client.url === url) || windows[0];
        if (existing) {
          try {
            const focused = await existing.focus();
            if (focused && focused.url !== url && 'navigate' in focused) {
              await focused.navigate(url);
            }
            return;
          } catch (err) {
            // The window can't be focused or navigated (e.g. not controlled yet): open a new one.
          }
        }
      }
      if (self.clients.openWindow) {
        await self.clients.openWindow(url);
      }
    })()
  );
});
