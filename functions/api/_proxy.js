// Cloudflare Pages Function helper (not routed — leading underscore).
//
// Proxies the Tankerkoenig API from the same origin so the API key never
// reaches the browser. The key is read from the server-side environment
// secret TANKERKOENIG_KEY (set in the Cloudflare Pages dashboard), not from
// the repository. Only whitelisted parameters are forwarded, and each is
// validated, so this cannot be abused as a general open proxy.

const UPSTREAM = "https://creativecommons.tankerkoenig.de/json/";

function json(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

// Reject anything that is not a sane Tankerkoenig request.
function valid(endpoint, sp) {
  if (endpoint === "list.php") {
    const lat = parseFloat(sp.get("lat"));
    const lng = parseFloat(sp.get("lng"));
    const rad = parseFloat(sp.get("rad"));
    const type = sp.get("type");
    const sort = sp.get("sort");
    if (!isFinite(lat) || lat < -90 || lat > 90) return false;
    if (!isFinite(lng) || lng < -180 || lng > 180) return false;
    if (!isFinite(rad) || rad <= 0 || rad > 25) return false;
    if (type && !["diesel", "e5", "e10", "all"].includes(type)) return false;
    if (sort && !["dist", "price"].includes(sort)) return false;
    return true;
  }
  if (endpoint === "prices.php") {
    const ids = sp.get("ids") || "";
    const parts = ids.split(",").filter(Boolean);
    if (!parts.length || parts.length > 30) return false;
    return parts.every((id) => /^[0-9a-fA-F-]{6,40}$/.test(id));
  }
  return false;
}

export async function proxy(context, endpoint, allowed) {
  const { request, env } = context;
  const key = env && env.TANKERKOENIG_KEY;
  if (!key) {
    // Same {ok:false, message} shape the client already handles.
    return json(
      { ok: false, message: "API-Schlüssel serverseitig nicht konfiguriert (TANKERKOENIG_KEY)." },
      500
    );
  }

  const inUrl = new URL(request.url);
  const out = new URL(UPSTREAM + endpoint);
  for (const p of allowed) {
    const v = inUrl.searchParams.get(p);
    if (v != null && v !== "") out.searchParams.set(p, v);
  }
  if (!valid(endpoint, out.searchParams)) {
    return json({ ok: false, message: "Ungültige Anfrageparameter." }, 400);
  }
  out.searchParams.set("apikey", key);

  let upstream;
  try {
    // Let Cloudflare's edge cache absorb repeated identical requests.
    upstream = await fetch(out.toString(), { cf: { cacheTtl: 120, cacheEverything: true } });
  } catch (e) {
    return json({ ok: false, message: "Tankerkönig-API nicht erreichbar." }, 502);
  }

  const body = await upstream.text();
  return new Response(body, {
    status: upstream.status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "public, max-age=120",
    },
  });
}
