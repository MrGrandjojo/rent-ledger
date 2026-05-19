"""Single shared slowapi Limiter — referenced by routes and registered on
the FastAPI app in main.py. Identifies clients by the first IP in
X-Forwarded-For if present (set by the nginx front), else falls back to
request.client.host.
"""

from fastapi import Request
from slowapi import Limiter


def _key_func(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "anonymous"


limiter = Limiter(key_func=_key_func)
