"""
Minimal Microsoft Graph client for uploading files to a OneDrive account
using the OAuth2 client-credentials flow (app-only, no signed-in user —
required since backups run unattended on a schedule).

Needs an Azure AD app registration with the Application permission
`Files.ReadWrite.All` (admin-consented) on Microsoft Graph, plus the id of
the OneDrive whose files that app is allowed to touch (ONEDRIVE_USER_ID).
Uses `requests` directly rather than the `msal` package to avoid adding a
new dependency for what is a two-endpoint integration.
"""
import os
import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MiB, must be a multiple of 320 KiB per Graph docs


class OneDriveConfigError(Exception):
    """Raised when required Azure/OneDrive config is missing."""


class OneDriveClient:
    def __init__(self, app):
        self.tenant_id = app.config.get("AZURE_TENANT_ID")
        self.client_id = app.config.get("AZURE_CLIENT_ID")
        self.client_secret = app.config.get("AZURE_CLIENT_SECRET")
        self.user_id = app.config.get("ONEDRIVE_USER_ID")
        self.folder = app.config.get("ONEDRIVE_BACKUP_FOLDER") or "Anchorstone-DB-Backups"

        missing = [
            name
            for name, val in [
                ("AZURE_TENANT_ID", self.tenant_id),
                ("AZURE_CLIENT_ID", self.client_id),
                ("AZURE_CLIENT_SECRET", self.client_secret),
                ("ONEDRIVE_USER_ID", self.user_id),
            ]
            if not val
        ]
        if missing:
            raise OneDriveConfigError(
                f"Missing OneDrive/Azure config: {', '.join(missing)}. "
                "Set these environment variables to enable backups."
            )

    def _get_access_token(self) -> str:
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        resp = requests.post(
            url,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def upload_file(self, local_path: str, remote_filename: str) -> dict:
        """
        Uploads local_path to /{folder}/{remote_filename} in the configured
        OneDrive account via a resumable upload session (works for any file size).

        Returns the Graph driveItem dict (has 'id', 'webUrl', 'size', ...).
        """
        token = self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        item_path = f"{self.folder}/{remote_filename}"
        session_resp = requests.post(
            f"{GRAPH_BASE}/users/{self.user_id}/drive/root:/{item_path}:/createUploadSession",
            headers=headers,
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=30,
        )
        session_resp.raise_for_status()
        upload_url = session_resp.json()["uploadUrl"]

        file_size = os.path.getsize(local_path)
        with open(local_path, "rb") as f:
            start = 0
            last_resp = None
            while start < file_size:
                chunk = f.read(UPLOAD_CHUNK_SIZE)
                end = start + len(chunk) - 1
                last_resp = requests.put(
                    upload_url,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                    },
                    data=chunk,
                    timeout=300,
                )
                last_resp.raise_for_status()
                start += len(chunk)

        return last_resp.json()
