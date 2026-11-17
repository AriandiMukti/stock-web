// Minimal service worker — its only job is to exist, since browsers
// require a registered service worker with a fetch handler before they
// offer "Add to Home Screen" / install. No offline caching: every request
// just passes straight through to the network, since login-gated pages
// wouldn't work offline anyway.
self.addEventListener('fetch', function (event) {
    event.respondWith(fetch(event.request));
});
