"""Send events to Azure Event Hubs over HTTPS (standard library only).

Connection string: Endpoint=sb://<ns>.servicebus.windows.net/;SharedAccessKeyName=<n>;SharedAccessKey=<k>[;EntityPath=<hub>]
"""

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

MAX_BATCH_BYTES = 200_000  # Basic tier accepts 256 KB per request


class EventHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class Hub:
    host: str
    key_name: str
    key: str
    name: str

    @property
    def url(self) -> str:
        return f"https://{self.host}/{self.name}"


def parse_connection(conn: str, hub_name: str | None = None) -> Hub:
    parts = dict(p.split("=", 1) for p in conn.strip().strip(";").split(";") if "=" in p)
    try:
        host = urllib.parse.urlsplit(parts["Endpoint"]).hostname
        name = hub_name or parts.get("EntityPath")
        if not host or not name:
            raise KeyError("Endpoint/EntityPath")
        return Hub(host, parts["SharedAccessKeyName"], parts["SharedAccessKey"], name)
    except KeyError as e:
        raise EventHubError(f"Event Hubs connection string is missing {e}") from None


def sas_token(hub: Hub, ttl: int = 3600, now: float | None = None) -> str:
    uri = urllib.parse.quote_plus(hub.url)
    expiry = int((now if now is not None else time.time()) + ttl)
    sig = base64.b64encode(hmac.new(hub.key.encode(), f"{uri}\n{expiry}".encode(), hashlib.sha256).digest())
    return f"SharedAccessSignature sr={uri}&sig={urllib.parse.quote_plus(sig)}&se={expiry}&skn={hub.key_name}"


def batches(bodies: list[str], max_bytes: int = MAX_BATCH_BYTES, max_events: int = 500):
    """Split event bodies into requests that fit the size limit."""
    cur, size = [], 2
    for b in bodies:
        n = len(b.encode()) + 16
        if cur and (size + n > max_bytes or len(cur) >= max_events):
            yield cur
            cur, size = [], 2
        cur.append(b)
        size += n
    if cur:
        yield cur


def send(hub: Hub, bodies: list[str], timeout: float = 30) -> int:
    """Send event bodies (strings). Returns the number of requests made."""
    n = 0
    token = sas_token(hub)
    for chunk in batches(bodies):
        data = json.dumps([{"Body": b} for b in chunk]).encode()
        req = urllib.request.Request(
            f"{hub.url}/messages?timeout=60&api-version=2014-01", data=data, method="POST",
            headers={"Authorization": token, "Content-Type": "application/vnd.microsoft.servicebus.json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read()
        except urllib.error.HTTPError as e:
            raise EventHubError(f"Event Hubs answered {e.code}: {e.read()[:200]!r}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise EventHubError(f"Event Hubs not reachable: {e}") from None
        n += 1
    return n
