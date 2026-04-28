// Jarvis Service Worker — offline support + PWA install

const CACHE_NAME = 'jarvis-v4';
const STATIC_ASSETS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/voice.js',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Tell all tabs to reload when a new SW takes over
self.addEventListener('activate', () => {
  self.clients.matchAll({ type: 'window' }).then(clients => {
    clients.forEach(client => client.postMessage({ type: 'SW_UPDATED' }));
  });
});

self.addEventListener('fetch', (event) => {
  // Skip API and WebSocket — always network
  if (event.request.url.includes('/api/') || event.request.url.includes('/ws')) {
    return;
  }

  // NETWORK FIRST for all assets — cache is fallback only
  // This ensures hard refresh always gets fresh code
  event.respondWith(
    fetch(event.request).then((response) => {
      if (response.ok) {
        const clone = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
      }
      return response;
    }).catch(() => {
      // Network failed — serve from cache (offline fallback)
      return caches.match(event.request);
    })
  );
});
