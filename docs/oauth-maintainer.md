# OAuth applications for EverySync maintainers

This setup is performed once by the release maintainer. End users of a
configured release use the sign-in buttons; they do not register applications.
No Google application has been registered for this repository yet. The shipped
`src/oauth-apps.json` is `{}`, so Google sign-in is unavailable by default.

## Google desktop application

1. In [Google Cloud Console](https://console.cloud.google.com/), create/select
   the EverySync project and enable Google Drive API.
2. Configure the consent screen with EverySync's identity, support contact,
   privacy information and intended audience. For development, add test users.
3. Create OAuth credentials with application type **Desktop app**. EverySync
   uses Google's supported loopback callback on `127.0.0.1` with an ephemeral
   port and S256 PKCE. Do not register this as a web or confidential application.
4. Put the desktop application metadata in `src/oauth-apps.json` before building:

   ```json
   {
     "drive": {
       "client_id": "YOUR-DESKTOP-CLIENT-ID.apps.googleusercontent.com",
       "client_secret": "YOUR-DESKTOP-CLIENT-SECRET"
     }
   }
   ```

5. The existing arbitrary-folder sync requires
   `https://www.googleapis.com/auth/drive`. Complete Google's applicable
   restricted-scope verification and consent publication before distributing
   broadly. Testing-mode consent is for test accounts, and its refresh-token
   limitations make it unsuitable for a production background-sync release.
   Do not silently substitute `drive.file`: it changes which existing folders
   and files EverySync can access.
6. Build the Windows release normally. PyInstaller includes this file under
   `src/`. Verify sign-in, folder listing/creation, cancellation, app restart,
   token renewal and sync with a disposable account/folder. Record live
   acceptance separately; automated tests cannot certify provider approval.

Desktop client metadata is public application identity. A desktop client secret
cannot be kept confidential in a distributed executable. Never place user access
tokens, refresh tokens, authorization codes, or a service-account key in this
file. Tokens remain in EverySync's encrypted, DPAPI-protected rclone config.
Do not edit an installed metadata file and claim the source release is enabled;
configure and verify the metadata included in the actual build.

## Microsoft and Dropbox

Without custom identities these use rclone's built-in applications; consent may
therefore show rclone. To display EverySync as the registered application,
register compatible desktop applications with each provider, then add entries
named `onedrive` and `dropbox`, each containing `client_id` and, where needed,
`client_secret`. Use the callback expected by rclone for that provider; Google's
separate PKCE callback does not change the rclone callback for other providers.
Verify public account/audience access and the provider's production permissions.

Custom app fields entered under **Advanced settings** override the complete
bundled application identity; EverySync does not mix credentials from two apps.
These fields are optional for Microsoft and Dropbox. Existing saved connections
keep their stored identity and tokens when a release adds new application
metadata; the metadata applies when connecting a new account.

References: [Google native OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[Drive scopes and verification](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
[rclone OneDrive registration](https://rclone.org/onedrive/#getting-your-own-client-id-and-key),
[rclone Dropbox](https://rclone.org/dropbox/).
