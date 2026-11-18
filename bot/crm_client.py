"""Minimal machine-to-machine client for optional demo CRM submissions."""
import json
import http.client
import re
import urllib.error
import urllib.parse
import urllib.request

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")
REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9-]{1,32}\Z")

class CRMTransferError(Exception):
    """A submission could not be verified; its idempotency key must be retained."""

def validate_config(url, token):
    if not url and not token:
        return None
    if not url or not token or not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("CRM_API_URL and a valid CRM_API_TOKEN must be configured together.")
    try:
        parts = urllib.parse.urlsplit(url)
        if (not parts.hostname or not re.fullmatch(r"[A-Za-z0-9.:-]+", parts.hostname)
                or parts.username is not None or parts.password is not None or parts.query or parts.fragment
                or "\\" in url or any(c.isspace() or ord(c) < 32 for c in url)):
            raise ValueError
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "::1")):
            raise ValueError
        _ = parts.port
    except ValueError:
        raise ValueError("CRM_API_URL must use HTTPS, or HTTP on the local loopback address, without credentials or query parameters.") from None
    return url, token

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class CRMClient:
    def __init__(self, url, token):
        self.url, self.token = validate_config(url, token)
        # Do not forward the service credential through a proxy or redirect.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def quotes(self, checkin, checkout, guests):
        query = urllib.parse.urlencode({"checkin": checkin, "checkout": checkout, "guests": guests})
        url = urllib.parse.urljoin(self.url, "/api/guest/quotes/") + "?" + query
        try:
            with self.opener.open(urllib.request.Request(url), timeout=8) as result:
                rows = json.loads(result.read(8193))["rooms"]
            if not isinstance(rows, list) or not all(isinstance(r, dict) and isinstance(r.get("id"), str)
                    and isinstance(r.get("name"), str) and type(r.get("nightly_cents")) is int
                    and type(r.get("total_cents")) is int for r in rows):
                raise ValueError
            return rows
        except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError):
            raise CRMTransferError("Could not check demo availability.") from None

    def submit(self, payload, key):
        request = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "Authorization": f"Bearer {self.token}", "Idempotency-Key": key,
        })
        try:
            with self.opener.open(request, timeout=8) as result:
                if result.status not in (200, 201):
                    raise CRMTransferError
                body = result.read(8193)
                if len(body) > 8192:
                    raise CRMTransferError
                data = json.loads(body)
            if (not isinstance(data, dict) or data.get("demo") is not True
                    or not isinstance(data.get("reference"), str) or not REFERENCE_PATTERN.fullmatch(data["reference"])):
                raise CRMTransferError
            return data["reference"]
        except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError, ValueError, TypeError, CRMTransferError):
            # Avoid displaying secrets, URLs or response bodies in logs or chats.
            raise CRMTransferError("Could not confirm the demo submission.") from None
