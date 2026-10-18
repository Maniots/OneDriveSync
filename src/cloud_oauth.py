"""Initial desktop OAuth only; rclone owns token persistence and refresh."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import webbrowser


_APP_PROVIDERS = frozenset(('drive', 'onedrive', 'dropbox'))
_APP_FIELDS = frozenset(('client_id', 'client_secret'))
_AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'
_TOKEN_ENDPOINT = 'https://oauth2.googleapis.com/token'
_CALLBACK_PATH = '/oauth/callback'
_CALLBACK_MESSAGE = b'Sign-in received. You can return to EverySync.'


def _app_parameters(value):
    if not isinstance(value, dict) or value.keys() - _APP_FIELDS:
        raise ValueError('Invalid OAuth application configuration.')
    if not value.get('client_id'):
        raise ValueError('The Google sign-in application has not been configured by the maintainer.')
    for key, item in value.items():
        if (not isinstance(item, str) or not item.strip() or len(item) > 8192
                or any(ord(character) < 32 for character in item)):
            raise ValueError('Invalid OAuth application configuration.')
    return dict(value)


def _unique_json_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError
    return result


def load_oauth_apps(path=None):
    """Read public desktop application metadata shipped beside this module.

    This file is maintained by EverySync, and must never contain user tokens.
    Frozen builds preserve the same src/ layout beside the bundled module.
    """
    path = Path(path) if path is not None else Path(__file__).with_name('oauth-apps.json')
    try:
        with path.open('rb') as handle:
            raw = handle.read(65537)
        if len(raw) > 65536:
            raise ValueError
        value = json.loads(raw, object_pairs_hook=_unique_json_object)
        if not isinstance(value, dict) or value.keys() - _APP_PROVIDERS:
            raise ValueError
        return {provider: _app_parameters(parameters) for provider, parameters in value.items()}
    except (OSError, ValueError, TypeError, UnicodeError):
        raise ValueError('Invalid OAuth application configuration. Contact the application maintainer.') from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        # Codes, verifiers and desktop metadata may only reach Google's endpoint.
        return None


def _exchange_token(parameters, timeout):
    request = Request(_TOKEN_ENDPOINT, data=urlencode(parameters).encode('ascii'),
                      headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'})
    with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
        raw = response.read(65537)
    if len(raw) > 65536:
        raise ValueError
    return json.loads(raw)


def _normalize_token(value):
    if not isinstance(value, dict):
        raise ValueError
    result = {}
    for key in ('access_token', 'refresh_token', 'token_type'):
        item = value.get(key)
        if (not isinstance(item, str) or not item.strip() or len(item) > 32768
                or any(ord(character) < 32 for character in item)):
            raise ValueError
        result[key] = item
    if result['token_type'].lower() != 'bearer':
        raise ValueError
    result['token_type'] = 'Bearer'
    expires = value.get('expires_in')
    if isinstance(expires, bool):
        raise ValueError
    expires = float(expires)
    if not math.isfinite(expires) or not 0 < expires <= 31536000:
        raise ValueError
    result['expiry'] = (datetime.now(timezone.utc) + timedelta(seconds=expires)).isoformat().replace('+00:00', 'Z')
    return result


def google_login(parameters, cancel_event, *, timeout=180, open_browser=None,
                 exchange=None, on_browser=None):
    """Authorize a Google desktop app and return a validated rclone token.

    The optional browser and exchange functions allow deterministic local tests.
    Call on_browser with the authorization URL if the UI offers a browser retry.
    All provider/network failures are replaced with safe, user-facing messages.
    """
    parameters = _app_parameters(parameters)
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Invalid sign-in timeout.')
    deadline = time.monotonic() + timeout
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
    received = threading.Event()
    result = {}
    result_lock = threading.Lock()

    class CallbackHandler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(.5)
            super().setup()

        def log_message(self, *args):
            # The standard HTTP logger includes authorization query parameters.
            pass

        def _reply(self, status):
            self.send_response(status)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(_CALLBACK_MESSAGE)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(_CALLBACK_MESSAGE)

        def send_error(self, code, message=None, explain=None):
            self._reply(405 if code == 501 else 400)

        def do_GET(self):
            try:
                address = urlsplit(self.path)
                if address.path != _CALLBACK_PATH:
                    self._reply(404)
                    return
                if (len(self.path) > 16384 or address.fragment
                        or re.search(r'%(?![0-9a-fA-F]{2})', address.query)):
                    raise ValueError
                pairs = parse_qsl(address.query, keep_blank_values=True,
                                  strict_parsing=True, errors='strict', max_num_fields=20)
                values = dict(pairs)
                if len(values) != len(pairs):
                    raise ValueError
                supplied_state = values.get('state', '')
                if (not 32 <= len(supplied_state) <= 256
                        or not secrets.compare_digest(supplied_state.encode('utf-8'), state.encode('ascii'))):
                    self._reply(403)
                    return
                code, error = values.get('code'), values.get('error')
                if (('code' in values) == ('error' in values)
                        or code is not None and not 1 <= len(code) <= 8192
                        or error is not None and not 1 <= len(error) <= 256):
                    raise ValueError
                with result_lock:
                    if received.is_set():
                        self._reply(400)
                        return
                    result.update({'error': True} if error is not None else {'code': code})
                    self._reply(403 if error is not None else 200)
                    received.set()
            except (ValueError, UnicodeError):
                self._reply(400)
            except (OSError, TimeoutError):
                pass

        def _wrong_method(self):
            self._reply(405)

        do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_TRACE = do_CONNECT = _wrong_method

    class CallbackServer(ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            # Never write provider payloads or callback request details to stderr.
            pass

    try:
        server = CallbackServer(('127.0.0.1', 0), CallbackHandler)
    except OSError:
        raise ValueError('Could not start browser sign-in. Try again.') from None
    server_thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    server_thread.start()
    redirect_uri = f'http://127.0.0.1:{server.server_port}{_CALLBACK_PATH}'
    authorization = _AUTH_ENDPOINT + '?' + urlencode({
        'client_id': parameters['client_id'], 'redirect_uri': redirect_uri,
        'response_type': 'code', 'scope': 'https://www.googleapis.com/auth/drive',
        'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
        'access_type': 'offline', 'prompt': 'consent',
    })

    def check_pending():
        if cancel_event.is_set():
            raise ValueError('Sign-in cancelled.')
        if time.monotonic() >= deadline:
            raise ValueError('Sign-in expired. Please try again.')

    try:
        check_pending()
        try:
            if on_browser is not None:
                on_browser(authorization)
            opened = (open_browser or webbrowser.open)(authorization)
        except Exception:
            raise ValueError('Could not open the browser for sign-in. Please try again.') from None
        if opened is False:
            raise ValueError('Could not open the browser for sign-in. Please try again.')
        while not received.wait(.05):
            check_pending()
        check_pending()
        if result.get('error'):
            raise ValueError('Google sign-in was denied. Please try again.')
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1)

    exchange_done = threading.Event()
    exchange_result = {}
    exchange_timeout = min(10., deadline - time.monotonic())
    check_pending()

    def exchange_worker():
        try:
            exchange_result['token'] = _normalize_token((exchange or _exchange_token)({
                **parameters, 'code': result['code'], 'code_verifier': verifier,
                'redirect_uri': redirect_uri, 'grant_type': 'authorization_code',
            }, exchange_timeout))
        except Exception:
            exchange_result['failed'] = True
        finally:
            exchange_done.set()

    # Never block the caller on a provider, including while cancelling. Only this
    # caller may publish the token; a cancelled worker cannot persist anything.
    worker = threading.Thread(target=exchange_worker, daemon=True)
    worker.start()
    exchange_deadline = time.monotonic() + exchange_timeout
    while not exchange_done.wait(.05):
        check_pending()
        if time.monotonic() >= exchange_deadline:
            raise ValueError('Google sign-in could not be completed. Please try again.')
    check_pending()
    if exchange_result.get('failed'):
        raise ValueError('Google sign-in could not be completed. Please try again.') from None
    return exchange_result['token']
