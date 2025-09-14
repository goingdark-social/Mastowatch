"""Type-safe Mastodon client using generated OpenAPI client with fallback to raw HTTP calls.

This provides the best type safety where available, flexibility where needed.
"""

import hashlib
import logging
import re
from typing import Any

import httpx
from app.clients.mastodon import AuthenticatedClient
from app.clients.mastodon.api.accounts.get_account import sync as get_account_sync
from app.clients.mastodon.api.accounts.get_account_statuses import (
    sync as get_account_statuses_sync,
)
from app.clients.mastodon.api.accounts.get_accounts_verify_credentials import (
    asyncio as get_accounts_verify_credentials_async,
)
from app.clients.mastodon.api.instance.get_instance import sync as get_instance_sync
from app.clients.mastodon.api.instance.get_instance_rules import (
    sync as get_instance_rules_sync,
)
from app.clients.mastodon.api.reports.create_report import sync as create_report_sync
from app.clients.mastodon.models.create_report_body import CreateReportBody
from app.config import get_settings
from app.metrics import api_call_seconds, http_errors
from app.rate_limit import throttle_if_needed, update_from_headers

settings = get_settings()
logger = logging.getLogger(__name__)


class MastoClient:
    """Enhanced Mastodon client with type safety and fallback support.

    Uses the generated OpenAPI client for documented endpoints while maintaining
    backward compatibility for admin endpoints and custom functionality.
    """

    def __init__(self, token: str):
        self._token = token
        self._base_url = str(settings.INSTANCE_BASE).rstrip("/")
        self._ua = settings.USER_AGENT
        self._timeout = settings.HTTP_TIMEOUT
        tok = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self._bucket_key = f"{self._base_url}:{tok}"

        self._api_client = AuthenticatedClient(
            base_url=self._base_url,
            token=token,
            headers={"User-Agent": self._ua},
            timeout=self._timeout,
        )

    def _parse_next_cursor(self, link_header: str | None) -> str | None:
        """Parse the Link header to extract the next_max_id for pagination."""
        if not link_header:
            return None

        for link in link_header.split(","):
            if 'rel="next"' in link:
                match = re.search(r"max_id=(\d+)", link)
                if match:
                    return match.group(1)
        return None

    def _make_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        throttle_if_needed(self._bucket_key)
        headers = {"Authorization": f"Bearer {self._token}", "User-Agent": self._ua}
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        url = f"{self._base_url}{path}"
        with api_call_seconds.labels(endpoint=path).time():
            response = httpx.request(
                method,
                url,
                headers=headers,
                timeout=self._timeout,
                **kwargs,
            )

        update_from_headers(self._bucket_key, response.headers)
        if response.status_code >= 400:
            http_errors.labels(endpoint=path, code=str(response.status_code)).inc()
        response.raise_for_status()
        return response

    async def verify_credentials(self) -> dict[str, Any]:
        """Verify the current token and return the associated account."""
        result = await get_accounts_verify_credentials_async(client=self._api_client)
        if result is None:
            raise ValueError("Failed to verify credentials: API returned None")
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return self._to_dict(result)

    @classmethod
    async def exchange_code_for_token(
        cls, code: str, redirect_uri: str
    ) -> dict[str, Any]:
        """Exchange an OAuth code for an access token."""
        settings_local = get_settings()

        # Validate required OAuth settings
        if not settings_local.OAUTH_CLIENT_ID:
            raise ValueError("OAUTH_CLIENT_ID is not configured")
        if not settings_local.OAUTH_CLIENT_SECRET:
            raise ValueError("OAUTH_CLIENT_SECRET is not configured")

        data = {
            "client_id": settings_local.OAUTH_CLIENT_ID,
            "client_secret": settings_local.OAUTH_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        }
        base = str(settings_local.INSTANCE_BASE).rstrip("/")
        bucket = f"{base}:oauth"
        throttle_if_needed(bucket)
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }

        # Debug logging to help troubleshoot OAuth issues
        client_id_preview = (
            settings_local.OAUTH_CLIENT_ID[:10]
            if settings_local.OAUTH_CLIENT_ID
            else "None"
        )
        logger.info(
            f"OAuth token exchange attempt - redirect_uri: {redirect_uri}, client_id: {client_id_preview}..."
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            with api_call_seconds.labels(endpoint="/oauth/token").time():
                response = await client.post(
                    f"{base}/oauth/token", data=data, headers=headers
                )
        update_from_headers(bucket, response.headers)
        if response.status_code >= 400:
            http_errors.labels(
                endpoint="/oauth/token", code=str(response.status_code)
            ).inc()
            # Handle potential encoding issues in error response
            try:
                error_text = response.text
            except (UnicodeDecodeError, Exception):
                # Fallback for compressed or binary responses
                error_text = str(response.content)
            logger.error(
                f"OAuth token exchange failed: {response.status_code} - {error_text}"
            )
            logger.error(
                f"Request data: client_id={client_id_preview}, redirect_uri={redirect_uri}, "
                f"grant_type=authorization_code"
            )
        response.raise_for_status()
        try:
            return response.json()
        except Exception as e:
            logger.error(f"Failed to parse OAuth response as JSON: {e}")
            logger.error(
                f"Response content type: {response.headers.get('content-type')}"
            )
            logger.error(f"Response encoding: {response.encoding}")
            raise ValueError(
                "Authentication failed due to server response encoding issue"
            ) from e

    def get_account(self, account_id: str) -> dict[str, Any]:
        """Get account information using generated OpenAPI client."""
        throttle_if_needed(self._bucket_key)

        with api_call_seconds.labels(endpoint=f"/api/v1/accounts/{account_id}").time():
            result = get_account_sync(id=account_id, client=self._api_client)

        if result is None:
            raise httpx.HTTPStatusError(
                "Account not found", request=None, response=None
            )

        if hasattr(result, "to_dict"):
            return result.to_dict()
        else:
            return result.__dict__

    def get_account_statuses(
        self,
        account_id: str,
        limit: int = 20,
        max_id: str | None = None,
        exclude_reblogs: bool = False,
        exclude_replies: bool = False,
        only_media: bool = False,
        pinned: bool = False,
    ) -> list[dict[str, Any]]:
        """Get account statuses using generated OpenAPI client."""
        throttle_if_needed(self._bucket_key)

        with api_call_seconds.labels(
            endpoint=f"/api/v1/accounts/{account_id}/statuses"
        ).time():
            result = get_account_statuses_sync(
                id=account_id,
                client=self._api_client,
                limit=limit,
                max_id=max_id if max_id else None,
                exclude_reblogs=exclude_reblogs,
                exclude_replies=exclude_replies,
                only_media=only_media,
                pinned=pinned,
            )

        if result is None:
            return []

        statuses = []
        for status in result:
            if hasattr(status, "to_dict"):
                statuses.append(status.to_dict())
            else:
                statuses.append(status.__dict__)
        return statuses

    def create_report(
        self,
        account_id: str,
        comment: str,
        status_ids: list[str] | None = None,
        category: str = "other",
        forward: bool = False,
        rule_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a report using generated OpenAPI client."""
        throttle_if_needed(self._bucket_key)

        report_body = CreateReportBody(
            account_id=account_id,
            comment=comment,
            category=category,
            forward=forward,
            status_ids=status_ids or [],
            rule_ids=rule_ids or [],
        )

        with api_call_seconds.labels(endpoint="/api/v1/reports").time():
            result = create_report_sync(client=self._api_client, body=report_body)

        if result is None:
            raise Exception("Failed to create report")

        if hasattr(result, "to_dict"):
            return result.to_dict()
        else:
            return result.__dict__

    def get_admin_accounts(
        self,
        origin: str | None = None,
        status: str | None = None,
        limit: int = 50,
        max_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Get admin accounts using direct HTTP calls (admin endpoints not in OpenAPI spec)."""
        params = {"limit": limit}
        if origin:
            params["origin"] = origin
        if status:
            params["status"] = status
        if max_id:
            params["max_id"] = max_id

        response = self._make_request("GET", "/api/v1/admin/accounts", params=params)
        accounts = response.json()
        next_max_id = self._parse_next_cursor(response.headers.get("Link"))
        return accounts, next_max_id

    def get_instance_info(self) -> dict[str, Any]:
        """Return basic instance metadata."""
        result = get_instance_sync(client=self._api_client)
        if result is None:
            raise Exception("Failed to get instance info")
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return result.__dict__

    def get_instance_rules(self) -> list[dict[str, Any]]:
        """Return the set of instance rules."""
        result = get_instance_rules_sync(client=self._api_client)
        if result is None:
            return []
        rules: list[dict[str, Any]] = []
        for rule in result:
            if hasattr(rule, "to_dict"):
                rules.append(rule.to_dict())
            else:
                rules.append(self._to_dict(rule))
        return rules
