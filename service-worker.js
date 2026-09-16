const CACHE = "bank-insurance-exam-updates-v25";
const CORE = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
  "./app-icon.jpg",
  "./day-night.jpg"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);

  // Live JSON: network-first, then cached data.
  if (url.pathname.endsWith("/data/updates.json")) {
    event.respondWith(
      fetch(event.request, {cache:"no-store"}).then(response => {
        const copy=response.clone();
        caches.open(CACHE).then(c=>c.put(event.request,copy));
        return response;
      }).catch(()=>caches.match(event.request))
    );
    return;
  }

  event.respondWith(
    fetch(event.request).then(response => {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(event.request, copy));
      return response;
    }).catch(() => caches.match(event.request))
  );
});
\n\nself.addEventListener("push", event => {\n  let data={};\n  try{data=event.data?event.data.json():{};}catch(e){data={title:"Bank & Insurance Exam Updates",body:event.data?event.data.text():"New exam update"};}\n  const title=data.title||"Bank & Insurance Exam Updates";\n  const options={body:data.body||"A new official exam update is available.",icon:"./icon-192.png",badge:"./icon-192.png",tag:data.tag||"exam-update",renotify:true,data:{url:data.url||"./"},vibrate:[120,60,120]};\n  event.waitUntil(self.registration.showNotification(title,options));\n});\nself.addEventListener("notificationclick", event => {\n  event.notification.close();\n  const url=event.notification.data&&event.notification.data.url||"./";\n  event.waitUntil(clients.matchAll({type:"window",includeUncontrolled:true}).then(list=>{\n    for(const c of list){if("focus" in c){c.navigate(url);return c.focus();}}\n    if(clients.openWindow) return clients.openWindow(url);\n  }));\n});\n