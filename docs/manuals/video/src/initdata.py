"""JSON {tg_id: initData} для демо-аккаунтов, подписанный BOT_TOKEN контейнера."""
import hashlib, hmac, json, os, time
from urllib.parse import urlencode

LANG = os.environ.get("DEMO_LANG", "ru")
USERS = {
    "920000001": ("Дилноза", "Рахимова"),
    "920000004": ("Азиз", "Каримов"),
}
secret = hmac.new(b"WebAppData", os.environ["BOT_TOKEN"].encode(), hashlib.sha256).digest()
out = {}
for tid, (fn, ln) in USERS.items():
    user = json.dumps({"id": int(tid), "first_name": fn, "last_name": ln, "language_code": LANG},
                      ensure_ascii=False, separators=(",", ":"))
    fields = {"auth_date": str(int(time.time())), "query_id": "demo", "user": user}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    fields["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    out[tid] = urlencode(fields)
print(json.dumps(out))
