"""Display-only account metadata for existing OAuth connections."""
from __future__ import annotations

import json
from http.client import HTTPException
import re
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


_UNAVAILABLE = "Account details are unavailable. Verify access and retry."
_ENDPOINTS = {
    "drive": ("https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress)", None),
    "dropbox": ("https://api.dropboxapi.com/2/users/get_current_account", b"null"),
    "onedrive": ("https://graph.microsoft.com/v1.0/me/drives?$select=owner,driveType&$top=2", None),
}


class AccountIdentityError(Exception):
    """A provider profile was unavailable or malformed."""


def normalize_account_identity(value):
    """Allow only short plain display strings; discard all other profile data."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for field, limit in (("name", 200), ("email", 320)):
        text = value.get(field)
        if not isinstance(text, str):
            continue
        text = unicodedata.normalize("NFC", text)
        text = "".join(" " if unicodedata.category(char).startswith("C") else char for char in text)
        text = " ".join(text.split())[:limit].rstrip()
        if text:
            result[field] = text
    return result


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A bearer token must never follow a Location supplied by a server.
        if fp is not None:
            fp.close()
        raise AccountIdentityError(_UNAVAILABLE)


def _check_cancel(cancel_event):
    if cancel_event.is_set():
        raise AccountIdentityError("Account operation cancelled.")


def _profile_fields(provider, value):
    if not isinstance(value, dict):
        raise AccountIdentityError(_UNAVAILABLE)
    if provider == "drive":
        user = value.get("user", {})
        if not isinstance(user, dict):
            raise AccountIdentityError(_UNAVAILABLE)
        return {"name": user.get("displayName"), "email": user.get("emailAddress")}
    if provider == "dropbox":
        name = value.get("name", {})
        if not isinstance(name, dict):
            raise AccountIdentityError(_UNAVAILABLE)
        return {"name": name.get("display_name"), "email": value.get("email")}
    drives = value.get("value")
    if not isinstance(drives, list):
        raise AccountIdentityError(_UNAVAILABLE)
    if "@odata.nextLink" in value:
        return {}
    eligible = []
    for drive in drives:
        if not isinstance(drive, dict):
            raise AccountIdentityError(_UNAVAILABLE)
        if drive.get("driveType") not in ("personal", "business"):
            continue
        owner = drive.get("owner", {})
        user = owner.get("user", {}) if isinstance(owner, dict) else {}
        # Count eligible drives even when their owner has no display fields:
        # a second drive must not make an ambiguous identity appear unique.
        eligible.append(user if isinstance(user, dict) else {})
    if len(eligible) != 1:
        return {}
    return {"name": eligible[0].get("displayName"), "email": eligible[0].get("email")}


def fetch_account_identity(provider, access_token, cancel_event):
    """Fetch a fixed provider profile with bounded reads and no redirects."""
    if provider not in _ENDPOINTS:
        return {}
    _check_cancel(cancel_event)
    if (not isinstance(access_token, str) or not 1 <= len(access_token) <= 16384
            or re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", access_token) is None):
        raise AccountIdentityError(_UNAVAILABLE)
    url, body = _ENDPOINTS[provider]
    request = Request(url, data=body, headers={
        "Authorization": "Bearer " + access_token, "Accept": "application/json",
        "Content-Type": "application/json"})
    opener = build_opener(ProxyHandler({}), _RejectRedirect())
    deadline = time.monotonic() + 8
    try:
        with opener.open(request, timeout=4) as response:
            _check_cancel(cancel_event)
            if response.status != 200:
                raise AccountIdentityError(_UNAVAILABLE)
            chunks, size = [], 0
            while True:
                _check_cancel(cancel_event)
                if time.monotonic() >= deadline:
                    raise AccountIdentityError(_UNAVAILABLE)
                # read1 returns after one buffered/socket read. read(n) could
                # wait indefinitely for n bytes from a trickling response.
                chunk = response.read1(min(4096, 65537 - size))
                _check_cancel(cancel_event)
                if time.monotonic() >= deadline:
                    raise AccountIdentityError(_UNAVAILABLE)
                size += len(chunk)
                if size > 65536:
                    raise AccountIdentityError(_UNAVAILABLE)
                if not chunk:
                    break
                chunks.append(chunk)
            value = json.loads(b"".join(chunks).decode("utf-8"))
        _check_cancel(cancel_event)
        return normalize_account_identity(_profile_fields(provider, value))
    except HTTPError as error:
        error.close()
        raise AccountIdentityError(_UNAVAILABLE) from None
    except (URLError, HTTPException, OSError, ValueError, RecursionError):
        # Do not forward provider errors, request URLs or response bodies.
        raise AccountIdentityError(_UNAVAILABLE) from None
