// NutriTracker Service Worker
// Caches static assets for offline UI. API calls always go to network.

const CACHE_NAME = 'nutritracker-v3';
const STATIC_ASSETS = [
    '/',
    '/css/style.css',
    '/js/app.js',
    '/js/onboarding.js',
    '/js/dashboard.js',
    '/js/meals.js',
    '/js/chat.js',
    '/js/history.js',
    '/js/pwa.js',
    '/manifest.json',
    '/assets/favicon.svg',
];

// Install — cache static assets
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

// Fetch — network first for API, cache first for static assets
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Always go to network for API calls and uploads
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/uploads/')) {
        event.respondWith(fetch(event.request));
        return;
    }

    // Stale-while-revalidate for static assets
    // Serves cached version instantly, then updates cache in background
    event.respondWith(
        caches.open(CACHE_NAME).then(cache => {
            return cache.match(event.request).then(cached => {
                const fetchPromise = fetch(event.request).then(response => {
                    if (response.ok && response.type === 'basic') {
                        cache.put(event.request, response.clone());
                    }
                    return response;
                }).catch(() => null);

                // Return cached immediately, or wait for network
                return cached || fetchPromise;
            });
        }).catch(() => {
            // Offline fallback for navigation
            if (event.request.mode === 'navigate') {
                return caches.match('/');
            }
        })
    );
});
