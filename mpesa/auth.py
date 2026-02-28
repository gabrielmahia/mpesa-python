"""OAuth token management for Daraja API.

Daraja issues tokens with a 3600-second (1 hour) TTL.
This module caches tokens in memory and auto-refreshes 60 seconds before expiry,
so callers never manage token lifecycle.
"""
from __future__ import annotations
import base64
import time
import urllib.request
import urllib.error
import json
from dataclasses import dataclass

from mpesa.exceptions import AuthenticationError


@dataclass
class _TokenCache:
    access_token: str = ""
    expires_at: float = 0.0

    def is_valid(self) -> bool:
        return bool(self.access_token) and time.time() < self.expires_at - 60


class Auth:
    """Manages OAuth2 token lifecycle for Daraja v3.

    Tokens are cached per Auth instance. In multi-process deployments,
    each process maintains its own cache (Daraja allows concurrent tokens).
    """

    SANDBOX_URL = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    LIVE_URL = "https://api.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"

    def __init__(self, consumer_key: str, consumer_secret: str, sandbox: bool = True):
        self._key = consumer_key
        self._secret = consumer_secret
        self._sandbox = sandbox
        self._cache = _TokenCache()

    @property
    def _url(self) -> str:
        return self.SANDBOX_URL if self._sandbox else self.LIVE_URL

    def token(self) -> str:
        """Return a valid access token, refreshing if necessary."""
        if not self._cache.is_valid():
            self._refresh()
        return self._cache.access_token

    def _refresh(self) -> None:
        credentials = base64.b64encode(f"{self._key}:{self._secret}".encode()).decode()
        req = urllib.request.Request(
            self._url,
            headers={"Authorization": f"Basic {credentials}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode("utf-8", "ignore")
            raise AuthenticationError(
                f"Token request failed ({e.code}): {body}",
                code=str(e.code),
            ) from e
        except OSError as e:
            raise AuthenticationError(f"Network error during auth: {e}") from e

        token = data.get("access_token")
        expires_in = int(data.get("expires_in", 3600))
        if not token:
            raise AuthenticationError("No access_token in response", raw=data)

        self._cache.access_token = token
        self._cache.expires_at = time.time() + expires_in
