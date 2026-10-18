import base64
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

import pytest

from src.cloud_oauth import google_login, load_oauth_apps


def callback(url, **parameters):
    query = parse_qs(urlsplit(url).query)
    target = query['redirect_uri'][0]
    parameters.setdefault('state', query['state'][0])
    try:
        with urlopen(target + '?' + urlencode(parameters), timeout=2) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def test_default_metadata_is_valid_and_packaged():
    apps = load_oauth_apps()
    assert isinstance(apps, dict)
    assert set(apps) <= {'drive', 'onedrive', 'dropbox'}
    for parameters in apps.values():
        assert set(parameters) <= {'client_id', 'client_secret'}
        assert parameters['client_id'].strip()
    from pathlib import Path
    spec = Path('packaging/OneDrivePCSync.spec').read_text()
    assert 'oauth-apps.json' in spec


def test_empty_metadata_is_supported(tmp_path):
    path = tmp_path / 'oauth-apps.json'
    path.write_text('{}')
    assert load_oauth_apps(path) == {}


def test_metadata_accepts_only_public_app_fields(tmp_path):
    path = tmp_path / 'oauth-apps.json'
    path.write_text(json.dumps({'drive': {'client_id': 'desktop', 'client_secret': 'public'}}))
    assert load_oauth_apps(path)['drive']['client_id'] == 'desktop'
    for metadata in ({'unknown': {'client_id': 'value'}}, {'drive': {'token': 'private'}},
                     {'drive': {'client_id': ''}}, {'drive': {'client_id': 42}},
                     {'drive': {'client_id': 'x' * 8193}}):
        path.write_text(json.dumps(metadata))
        with pytest.raises(ValueError) as error:
            load_oauth_apps(path)
        assert 'private' not in str(error.value)


def test_metadata_rejects_duplicate_json_fields(tmp_path):
    path = tmp_path / 'oauth-apps.json'
    path.write_text('{"drive":{"client_id":"one","client_id":"two"}}')
    with pytest.raises(ValueError):
        load_oauth_apps(path)


@pytest.mark.parametrize('token_type', ['Bearer', 'bearer', 'BEARER'])
def test_login_uses_loopback_state_pkce_and_normalizes_token(token_type):
    captured = {}
    def browser(url):
        captured['url'] = url
        query = parse_qs(urlsplit(url).query)
        assert url.startswith('https://accounts.google.com/o/oauth2/v2/auth?')
        assert query['access_type'] == ['offline']
        assert query['prompt'] == ['consent']
        assert query['scope'] == ['https://www.googleapis.com/auth/drive']
        assert query['code_challenge_method'] == ['S256']
        assert len(query['state'][0]) >= 32
        redirect = urlsplit(query['redirect_uri'][0])
        assert redirect.hostname == '127.0.0.1' and redirect.port
        assert callback(url, code='test-code') == (200, b'Sign-in received. You can return to EverySync.')
        return True
    def exchange(parameters, timeout):
        captured['exchange'] = parameters
        assert 0 < timeout <= 10
        return {'access_token': 'access', 'refresh_token': 'refresh', 'token_type': token_type, 'expires_in': 3600}
    before = datetime.now(timezone.utc)
    token = google_login({'client_id': 'desktop', 'client_secret': 'public'}, threading.Event(),
                         open_browser=browser, exchange=exchange)
    data = captured['exchange']
    assert data['code'] == 'test-code'
    assert data['grant_type'] == 'authorization_code'
    challenge = base64.urlsafe_b64encode(hashlib.sha256(data['code_verifier'].encode()).digest()).decode().rstrip('=')
    assert parse_qs(urlsplit(captured['url']).query)['code_challenge'] == [challenge]
    assert token['refresh_token'] == 'refresh'
    assert token['token_type'] == 'Bearer'
    assert token['expiry'].endswith('Z')
    assert 3590 < (datetime.fromisoformat(token['expiry'].replace('Z', '+00:00')) - before).total_seconds() < 3610
    with pytest.raises(OSError):
        callback(captured['url'], code='test-code')


def test_invalid_callbacks_do_not_consume_login():
    def browser(url):
        assert callback(url, code='do-not-show', state='wrong')[0] == 403
        query = parse_qs(urlsplit(url).query)
        target = query['redirect_uri'][0]
        bad_urls = [target + '?state=' + query['state'][0] + '&code=one&code=two',
                    target + '?state=' + query['state'][0] + '&code=one&error=denied',
                    target + '?state=' + query['state'][0] + '&code=%ZZ',
                    target + '?code=one']
        for address in bad_urls:
            with pytest.raises(HTTPError) as error:
                urlopen(address, timeout=2)
            assert error.value.code in (400, 403)
        with pytest.raises(HTTPError) as error:
            urlopen(target.replace('/oauth/callback', '/other'), timeout=2)
        assert error.value.code == 404
        with pytest.raises(HTTPError) as error:
            urlopen(Request(target, data=b'code=one'), timeout=2)
        assert error.value.code == 405
        with pytest.raises(HTTPError) as error:
            urlopen(Request(target, method='PROPFIND'), timeout=2)
        assert error.value.code == 405
        assert callback(url, code='good')[0] == 200
        return True
    result = google_login({'client_id': 'desktop'}, threading.Event(), open_browser=browser,
                          exchange=lambda *_: {'access_token': 'ok', 'refresh_token': 'refresh', 'token_type': 'Bearer', 'expires_in': 60})
    assert result['access_token'] == 'ok'


def test_callback_matches_declared_contract_responses():
    from pathlib import Path
    contract = json.loads(Path('docs/contracts/oauth-callback.openapi.json').read_text())
    assert len(contract['paths']) == 1
    callback_path, operations = next(iter(contract['paths'].items()))
    assert set(operations) == {'get'}
    operation = operations['get']
    observed = set()
    def browser(url):
        query = parse_qs(urlsplit(url).query)
        target = query['redirect_uri'][0]
        parsed = urlsplit(target)
        assert parsed.path == callback_path
        assert f'{parsed.scheme}://{parsed.hostname}:{{port}}' == contract['servers'][0]['url']
        state_schema = next(item['schema'] for item in operation['parameters'] if item['name'] == 'state')
        assert state_schema['minLength'] <= len(query['state'][0]) <= state_schema['maxLength']
        requests = [
            (target + '?' + urlencode({'state': query['state'][0], 'code': ['one', 'two']}, doseq=True), None),
            (target + '?state=wrong&code=one', None),
            (target.replace(callback_path, '/other'), None),
            (target, 'POST'),
            (target + '?' + urlencode({'state': query['state'][0], 'code': 'one'}), None),
        ]
        for address, method in requests:
            try:
                with urlopen(Request(address, method=method), timeout=2) as response:
                    observed.add(str(response.status))
            except HTTPError as error:
                observed.add(str(error.code))
        return True
    google_login({'client_id': 'desktop'}, threading.Event(), open_browser=browser,
                 exchange=lambda *_: {'access_token': 'ok', 'refresh_token': 'refresh', 'token_type': 'Bearer', 'expires_in': 60})
    assert observed == set(operation['responses'])


@pytest.mark.parametrize('action, message', [('deny', 'denied'), ('timeout', 'expired'), ('cancel', 'cancelled'), ('browser', 'browser')])
def test_login_failure_states_are_safe(action, message):
    cancel = threading.Event()
    def browser(url):
        if action == 'deny':
            status, body = callback(url, error='access_denied', error_description='do-not-show')
            assert status == 403 and b'do-not-show' not in body
        if action == 'cancel':
            cancel.set()
        return action != 'browser'
    with pytest.raises(ValueError, match=message):
        google_login({'client_id': 'desktop'}, cancel, timeout=.1, open_browser=browser)


def test_exchange_is_cancellable_and_never_leaks_errors():
    cancel = threading.Event()
    started = threading.Event()
    def browser(url):
        callback(url, code='secret-code')
        return True
    def exchange(*args):
        started.set()
        cancel.set()
        time.sleep(.5)
        raise RuntimeError('secret-provider-body')
    before = time.monotonic()
    with pytest.raises(ValueError, match='cancelled'):
        google_login({'client_id': 'desktop'}, cancel, open_browser=browser, exchange=exchange)
    assert started.is_set() and time.monotonic() - before < .4


@pytest.mark.parametrize('response', [RuntimeError('secret-provider-body'), {'access_token': 'secret'},
    {'access_token': 'secret', 'refresh_token': 'refresh', 'expires_in': -1},
    {'access_token': 'secret', 'refresh_token': 'refresh', 'expires_in': float('inf')}])
def test_bad_exchange_result_is_redacted(response):
    def exchange(*args):
        if isinstance(response, Exception):
            raise response
        return response
    def browser(url):
        callback(url, code='secret-code')
        return True
    with pytest.raises(ValueError) as error:
        google_login({'client_id': 'desktop'}, threading.Event(), open_browser=browser, exchange=exchange)
    assert 'secret' not in str(error.value)


def test_real_exchange_uses_fixed_endpoint_and_bounded_form(monkeypatch):
    from src import cloud_oauth
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            assert limit == 65537
            return b'{"access_token":"access"}'
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == 'https://oauth2.googleapis.com/token'
            assert request.get_method() == 'POST'
            assert parse_qs(request.data.decode())['code'] == ['private-code']
            assert timeout == 3
            return Response()
    def opener(handler):
        assert issubclass(handler, cloud_oauth.HTTPRedirectHandler)
        assert handler().redirect_request(None, None, 302, '', {}, 'https://attacker.invalid') is None
        return Opener()
    monkeypatch.setattr(cloud_oauth, 'build_opener', opener)
    assert cloud_oauth._exchange_token({'code': 'private-code'}, 3) == {'access_token': 'access'}
