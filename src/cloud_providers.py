"""Curated provider setup fields; never expose arbitrary rclone options."""
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class SetupField:
    key: str
    label: str
    secret: bool = False
    required: bool = False


@dataclass(frozen=True)
class Provider:
    label: str
    hint: str
    fields: tuple = ()


PROVIDER_SETUP = {
    "local": Provider("Local folder / NAS", "Choose an existing folder. No cloud account is needed."),
    "onedrive": Provider("OneDrive online", "Sign in with Microsoft in your browser. Optional OAuth app credentials can be supplied below.", (
        SetupField("client_id", "Application client ID (optional)"), SetupField("client_secret", "Client secret (optional)", True))),
    "drive": Provider("Google Drive", "Create a Desktop OAuth client in Google Cloud with Drive API enabled, then sign in in your browser.", (
        SetupField("client_id", "OAuth client ID", required=True), SetupField("client_secret", "OAuth client secret", True, True))),
    "s3": Provider("Amazon S3 / compatible", "Root is bucket-name/prefix. Use an AWS profile or an access-key pair. A custom endpoint selects S3-compatible storage.", (
        SetupField("profile", "AWS profile (optional)"), SetupField("access_key_id", "Access key ID (optional)"),
        SetupField("secret_access_key", "Secret access key (optional)", True), SetupField("session_token", "Session token (optional)", True),
        SetupField("region", "Region (optional)"), SetupField("endpoint", "HTTPS endpoint (optional)"))),
    "sftp": Provider("SFTP", "Use a trusted known_hosts file to verify the server identity.", (
        SetupField("host", "Host", required=True), SetupField("user", "User", required=True),
        SetupField("port", "Port (optional)"), SetupField("pass", "Password (optional)", True),
        SetupField("key_file", "SSH private key file (optional)"), SetupField("known_hosts_file", "Known hosts file", required=True))),
    "webdav": Provider("WebDAV / Nextcloud", "Enter the HTTPS WebDAV endpoint and an account or app password.", (
        SetupField("url", "HTTPS WebDAV URL", required=True), SetupField("user", "User", required=True),
        SetupField("pass", "App password", True, True))),
    "dropbox": Provider("Dropbox", "Authorize access to Dropbox in your browser."),
    "azureblob": Provider("Azure Blob Storage", "Root is container-name/prefix.", (
        SetupField("account", "Storage account", required=True), SetupField("key", "Account key", True, True))),
    "b2": Provider("Backblaze B2", "Root is bucket-name/prefix. Use a scoped application key.", (
        SetupField("account", "Application key ID", required=True), SetupField("key", "Application key", True, True))),
}


def setup_parameters(provider, values):
    spec = PROVIDER_SETUP[provider]
    allowed = {field.key for field in spec.fields}
    if not isinstance(values, dict) or values.keys() - allowed:
        raise ValueError("Unsupported connection option.")
    result = {}
    for field in spec.fields:
        value = values.get(field.key, "")
        if not isinstance(value, str) or len(value) > 8192 or "\0" in value:
            raise ValueError("Invalid connection option.")
        if field.required and not value.strip():
            raise ValueError(f"{field.label} is required.")
        if value:
            result[field.key] = value
    for key in ("url", "endpoint"):
        if key in result:
            address = urlsplit(result[key])
            if address.scheme != "https" or not address.hostname or address.username or address.password:
                raise ValueError("Connection URLs must use HTTPS without embedded credentials.")
    if provider == "s3":
        if not result.get("profile") and not (result.get("access_key_id") and result.get("secret_access_key")):
            raise ValueError("Provide an AWS profile or both an access key ID and a secret access key.")
        result["provider"] = "Other" if result.get("endpoint") else "AWS"
        result["env_auth"] = "false" if result.get("access_key_id") else "true"
    if provider == "sftp":
        from pathlib import Path
        for key in ("known_hosts_file", "key_file"):
            if result.get(key) and not Path(result[key]).is_file():
                raise ValueError("The selected SSH key or known-hosts file does not exist.")
    if provider == "webdav":
        result["vendor"] = "other"
    return result
