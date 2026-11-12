// SS Deal Finder service worker: makes the app installable and lets it open without a connection.
// Network first for everything (so an update of the app shows up immediately), the last good copy when offline.
// The API is never cached: prices, listings and notifications are always live.
const CACHE = 'ssd-shell-v3';
const SHELL = ['./', 'index.html', 'css/base.css', 'css/fonts.css', 'js/app.js', 'js/core.js', 'js/theme.js', 'js/motion.js', 'js/bigpicture.js',
  'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', (e) => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;   // live data: straight to the network
  e.respondWith(fetch(req).then((res) => {
    if (res.ok && res.type === 'basic') { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); }
    return res;
  }).catch(() => caches.match(req).then((hit) => hit || (req.mode === 'navigate' ? caches.match('index.html') : Response.error()))));
});
