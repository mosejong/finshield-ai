/**
 * 서비스 워커.
 *
 * 목적은 하나다. 설치형으로 열었을 때 연결이 끊겨도 흰 화면 대신 쓸모 있는
 * 안내가 뜨게 하는 것. 오프라인 앱을 만드는 게 아니다.
 *
 * 캐시하지 않는 것을 먼저 정해 두고 시작했다.
 *   - 화면 HTML. 분석 결과에는 사용자가 붙여넣은 문자 원문이 들어 있다.
 *     이걸 디스크 캐시에 남기면 "세션에만 보관한다"는 약속이 깨진다.
 *   - `/api/*`. 오래된 위험 판정을 새 판정처럼 보여주는 것은 없느니만 못하다.
 *   - GET 이 아닌 요청 전부. 특히 공유 시트가 `/check/shared` 로 보내는 POST 는
 *     여기서 손대는 순간 본문이 사라진다.
 *
 * 그래서 캐시에 남는 것은 두 가지뿐이다. 해시가 붙어 내용이 바뀌지 않는 빌드
 * 산출물과 아이콘, 그리고 오프라인 안내 화면.
 */

const VERSION = "v1";
const SHELL_CACHE = `finshield-shell-${VERSION}`;
const STATIC_CACHE = `finshield-static-${VERSION}`;

const OFFLINE_URL = "/offline";
const PRECACHE = [
  OFFLINE_URL,
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      await cache.addAll(PRECACHE);
      // 오프라인 안내는 빨리 바뀔수록 좋다. 이전 워커가 물러나기를 기다리지 않는다.
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keep = new Set([SHELL_CACHE, STATIC_CACHE]);
      for (const key of await caches.keys()) {
        if (!keep.has(key)) await caches.delete(key);
      }
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // respondWith 를 부르지 않으면 브라우저가 평소대로 처리한다. 아래 조건들은
  // 전부 "우리가 개입하지 않는다" 는 뜻이다.
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch {
    return;
  }

  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (isImmutable(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(networkThenOffline(request));
  }
});

/** 내용이 바뀌면 경로도 바뀌는 것들. 그래서 캐시를 무효화할 일이 없다. */
function isImmutable(pathname) {
  return pathname.startsWith("/_next/static/") || pathname.startsWith("/icons/");
}

async function cacheFirst(request) {
  const cache = await caches.open(STATIC_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;

  const response = await fetch(request);
  if (response.ok && response.type === "basic") {
    // 응답 본문은 한 번만 읽을 수 있다. 캐시에는 복제본을 넣는다.
    cache.put(request, response.clone());
  }
  return response;
}

async function networkThenOffline(request) {
  try {
    const response = await fetch(request);
    refreshOfflinePage();
    return response;
  } catch {
    const cached = await caches.match(OFFLINE_URL, { cacheName: SHELL_CACHE });
    if (cached) return cached;
    return new Response(LAST_RESORT, {
      status: 503,
      headers: { "content-type": "text/html; charset=utf-8" },
    });
  }
}

let offlineRefreshed = false;

/**
 * 배포가 바뀌면 설치할 때 담아 둔 오프라인 화면이 옛 빌드의 스타일시트를
 * 가리키게 된다. 온라인일 때 한 번만 새로 받아 둔다. 실패는 무시한다 -
 * 있던 사본이 그대로 남는 편이 낫다.
 */
function refreshOfflinePage() {
  if (offlineRefreshed) return;
  offlineRefreshed = true;
  caches
    .open(SHELL_CACHE)
    .then((cache) => cache.add(OFFLINE_URL))
    .catch(() => {});
}

/** 오프라인 화면조차 캐시에 없을 때. 설치 직후 첫 요청이 실패한 경우 정도다. */
const LAST_RESORT = `<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>연결 없음 · FinShield</title></head>
<body style="margin:0;padding:24px;font:16px/1.6 system-ui,-apple-system,sans-serif;color:#16191f;background:#fff">
<p>인터넷에 연결되어 있지 않아 확인해 드리지 못했습니다. 확인하지 못했다는 것이 안전하다는 뜻은 아닙니다.</p>
<p>메시지의 링크를 누르지 말고, 상대가 말한 기관의 공식 대표번호로 직접 확인하세요.</p>
<p><a href="tel:112">112 경찰</a> · <a href="tel:1332">1332 금융감독원</a></p>
</body></html>`;
