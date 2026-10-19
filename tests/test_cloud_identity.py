import io
from http.client import IncompleteRead
import json
import threading
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request

import pytest

from src import cloud_identity


class Response(io.BytesIO):
    status = 200


def request_fixture(monkeypatch, value):
    body = json.dumps(value, ensure_ascii=False).encode()
    opener = Mock()
    opener.open.return_value = Response(body)
    factory = Mock(return_value=opener)
    monkeypatch.setattr(cloud_identity, "build_opener", factory, raising=False)
    return opener, factory


@pytest.mark.parametrize("provider,body,expected,url,method,data", [
    ("drive", {"user": {"displayName": "  Ada  Lovelace ", "emailAddress": " ada@example.test ",
                         "permissionId": "private-unused"}},
     {"name": "Ada Lovelace", "email": "ada@example.test"},
     "https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress)", "GET", None),
    ("dropbox", {"name": {"display_name": "Zoë"}, "email": "zoe@example.test", "account_id": "unused"},
     {"name": "Zoë", "email": "zoe@example.test"},
     "https://api.dropboxapi.com/2/users/get_current_account", "POST", b"null"),
    ("onedrive", {"value": [{"driveType": "business", "owner": {"user": {
        "displayName": "Éva", "email": "eva@example.test"}}}]},
     {"name": "Éva", "email": "eva@example.test"},
     "https://graph.microsoft.com/v1.0/me/drives?$select=owner,driveType&$top=2", "GET", None),
])
def test_identity_uses_only_fixed_profile_endpoint(monkeypatch, provider, body, expected, url, method, data):
    opener, _ = request_fixture(monkeypatch, body)
    assert cloud_identity.fetch_account_identity(provider, "fixture-token", threading.Event()) == expected
    request = opener.open.call_args.args[0]
    assert request.full_url == url
    assert request.get_method() == method
    assert request.data == data
    assert request.get_header("Authorization") == "Bearer fixture-token"
    assert 0 < opener.open.call_args.kwargs["timeout"] <= 5


@pytest.mark.parametrize("value,expected", [
    ({"name": " Alice\r\n\x00\u202e Smith\u2028 Jr ", "email": " a@example.test ", "token": "unused"},
     {"name": "Alice Smith Jr", "email": "a@example.test"}),
    ({"name": "x" * 201, "email": "y" * 321}, {"name": "x" * 200, "email": "y" * 320}),
    ({"name": "\t\x00", "email": None}, {}), ({"name": {}, "email": 1}, {}),
    ({"name": "Jose\u0301"}, {"name": "José"}),
])
def test_normalization_returns_only_bounded_single_line_display_fields(value, expected):
    assert cloud_identity.normalize_account_identity(value) == expected


@pytest.mark.parametrize("body", [
    {"value": []}, {"value": [{"driveType": "documentLibrary", "owner": {"user": {"displayName": "Shared owner"}}}]},
    {"value": [{"driveType": "personal", "owner": {"user": {"displayName": "A"}}},
               {"driveType": "business", "owner": {"user": {"displayName": "B"}}}]},
    {"value": [{"driveType": "personal", "owner": {"user": {"displayName": "A"}}}],
     "@odata.nextLink": "https://foreign.test/private"},
])
def test_microsoft_ambiguous_or_shared_identity_is_unavailable(monkeypatch, body):
    opener, _ = request_fixture(monkeypatch, body)
    assert cloud_identity.fetch_account_identity("onedrive", "fixture", threading.Event()) == {}
    assert opener.open.call_count == 1


def test_microsoft_unique_primary_ignores_shared_drive_owner_and_missing_email(monkeypatch):
    request_fixture(monkeypatch, {"value": [
        {"driveType": "documentLibrary", "owner": {"user": {"email": "shared@example.test"}}},
        {"driveType": "personal", "owner": {"user": {"displayName": "Signed in"}}}]})
    assert cloud_identity.fetch_account_identity("onedrive", "fixture", threading.Event()) == {"name": "Signed in"}


@pytest.mark.parametrize("token", ["", None, "fixture\r\nInjected: value", "nonascii-é", "two words"])
def test_invalid_bearer_token_never_reaches_network(monkeypatch, token):
    opener, _ = request_fixture(monkeypatch, {})
    with pytest.raises(cloud_identity.AccountIdentityError) as caught:
        cloud_identity.fetch_account_identity("drive", token, threading.Event())
    assert "fixture" not in str(caught.value)
    opener.open.assert_not_called()


@pytest.mark.parametrize("failure", [TimeoutError("private token"), URLError("private body"),
    HTTPError("https://private.test", 401, "private body", {}, io.BytesIO(b"private body")),
    IncompleteRead(b"private-partial")])
def test_network_failures_have_static_safe_errors(monkeypatch, failure):
    opener, _ = request_fixture(monkeypatch, {})
    opener.open.side_effect = failure
    with pytest.raises(cloud_identity.AccountIdentityError) as caught:
        cloud_identity.fetch_account_identity("drive", "fixture", threading.Event())
    assert "private" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("body", [b"x" * 65537, b"not json: private", b"[]", b"{\"user\":[]}", b"\xff"],
                         ids=["oversize", "invalid-json", "array", "invalid-user", "invalid-utf8"])
def test_malformed_or_oversize_profile_fails_safely(monkeypatch, body):
    opener, _ = request_fixture(monkeypatch, {})
    opener.open.return_value = Response(body)
    with pytest.raises(cloud_identity.AccountIdentityError) as caught:
        cloud_identity.fetch_account_identity("drive", "fixture", threading.Event())
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("when", ["before", "open", "read"])
def test_http_cancellation_before_and_between_bounded_reads(monkeypatch, when):
    event = threading.Event()
    opener, _ = request_fixture(monkeypatch, {"user": {"displayName": "Ada"}})
    if when == "before":
        event.set()
    elif when == "open":
        def open_response(*args, **kwargs):
            event.set()
            return Response(b"{}")
        opener.open.side_effect = open_response
    else:
        class CancellingResponse(Response):
            def read1(self, size=-1):
                event.set()
                return super().read1(size)
        opener.open.return_value = CancellingResponse(b" " * 8192)
    with pytest.raises(cloud_identity.AccountIdentityError, match="cancel"):
        cloud_identity.fetch_account_identity("drive", "fixture", event)
    if when == "before":
        opener.open.assert_not_called()


def test_redirect_handler_rejects_authorization_forwarding(monkeypatch):
    _, factory = request_fixture(monkeypatch, {})
    cloud_identity.fetch_account_identity("drive", "fixture", threading.Event())
    handlers = [item for item in factory.call_args.args if isinstance(item, HTTPRedirectHandler)]
    assert len(handlers) == 1
    response = Response(b"private")
    with pytest.raises(cloud_identity.AccountIdentityError):
        handlers[0].redirect_request(Request("https://www.googleapis.com", headers={"Authorization": "Bearer fixture"}),
                                     response, 302, "redirect", {}, "https://foreign.test")
    assert response.closed


def test_chunk_reader_checks_deadline_without_waiting_to_fill_buffer(monkeypatch):
    opener, _ = request_fixture(monkeypatch, {})
    class SlowResponse(Response):
        def read(self, size=-1):
            pytest.fail("read(n) may block while a peer trickles a whole buffer")
        def read1(self, size=-1):
            return b" "
    opener.open.return_value = SlowResponse(b"ignored")
    monkeypatch.setattr(cloud_identity.time, "monotonic", Mock(side_effect=[0, 0, 9]))
    with pytest.raises(cloud_identity.AccountIdentityError):
        cloud_identity.fetch_account_identity("drive", "fixture", threading.Event())


def test_nonmapping_normalization_and_missing_email_stay_explicit():
    for value in (None, [], "private", 12):
        assert cloud_identity.normalize_account_identity(value) == {}
    assert cloud_identity.normalize_account_identity({"name": "Ada"}) == {"name": "Ada"}


def test_unsupported_provider_never_opens_network(monkeypatch):
    opener, _ = request_fixture(monkeypatch, {})
    assert cloud_identity.fetch_account_identity("s3", "", threading.Event()) == {}
    opener.open.assert_not_called()


@pytest.mark.parametrize("provider,body", [
    ("onedrive", {"value": [{"driveType": [], "owner": {}}]}),
    ("onedrive", {"value": [{"driveType": "business", "owner": {"user": []}}]}),
    ("dropbox", {"name": []}),
])
def test_malformed_nested_fields_never_escape_raw_exceptions(monkeypatch, provider, body):
    request_fixture(monkeypatch, body)
    try:
        result = cloud_identity.fetch_account_identity(provider, "fixture", threading.Event())
    except cloud_identity.AccountIdentityError:
        return
    assert result == {}
