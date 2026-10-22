/* Same-origin application cache. Cache namespace follows the registration's path. */
const cacheName = 'rebang-v03-' + self.registration.scope + '-' + new URL(self.location.href).searchParams.get('scope');
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(cacheName);
    for (const path of ['index.html','visual-data.json','tokens.css','visual.css','visual.js','icons.js','icon-192.png']) {
      try { await cache.add(new URL(path, self.registration.scope)); } catch { /* One missing asset must not discard the readable cache. */ }
    }
    const document = await cache.match(new URL('index.html', self.registration.scope));
    if (document) {
      const html = await document.text();
      for (const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)) {
        const asset = new URL(match[1], self.registration.scope);
        if (asset.origin === self.location.origin && /\.(?:js|css|png|ico|svg)(?:\?|$)/.test(asset.href)) {
          try { await cache.add(asset); } catch { /* Preserve other cached assets. */ }
        }
      }
    }
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || !url.href.startsWith(self.registration.scope)) return;
  event.respondWith((async () => {
    const cache = await caches.open(cacheName);
    try {
      const response = await fetch(event.request);
      if (response.ok) await cache.put(event.request, response.clone());
      return response;
    } catch (error) {
      const cached = await cache.match(event.request);
      if (cached) return cached;
      if (event.request.mode === 'navigate') {
        const shell = await cache.match(new URL('index.html', self.registration.scope));
        if (shell) return shell;
      }
      throw error;
    }
  })());
});
