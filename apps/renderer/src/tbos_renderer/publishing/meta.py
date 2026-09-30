from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from tbos_renderer.config import Settings
from tbos_renderer.publishing.schemas import PublishResult

LOGGER = logging.getLogger(__name__)


class MetaPublishingError(Exception):
    """Base exception for Meta Graph API publishing failures."""


class MetaRateLimitError(MetaPublishingError):
    """Raised when Meta API rate limits are hit."""


class MetaContainerProcessingError(MetaPublishingError):
    """Raised when an Instagram container fails to process."""


class MetaGraphPublisher:
    """Client for publishing media to Facebook Pages and Instagram Business accounts."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
    ) -> None:
        self.settings = settings
        self._http_client = http_client
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.base_url = f"{settings.meta_api_base_url}/{settings.meta_api_version}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is not None:
            return self._http_client
        return httpx.AsyncClient(timeout=60.0)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        client = await self._get_client()
        backoff = self.initial_backoff

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    files=files,
                    headers=headers,
                )

                if response.status_code == 429:
                    if attempt == self.max_retries:
                        raise MetaRateLimitError("Meta API rate limit exceeded.")
                    LOGGER.warning("Meta rate limit encountered. Retrying in %.1fs...", backoff)
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                if response.status_code >= 500:
                    if attempt == self.max_retries:
                        raise MetaPublishingError(
                            f"Meta server error {response.status_code}: {response.text[:300]}"
                        )
                    LOGGER.warning(
                        "Meta 5xx error (%d). Retrying in %.1fs...", response.status_code, backoff
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                payload = response.json()
                if not response.is_success:
                    err = payload.get("error", {})
                    err_msg = err.get("message", response.text[:300])
                    err_code = err.get("code")
                    raise MetaPublishingError(f"Meta Graph API error (code {err_code}): {err_msg}")

                return payload  # type: ignore[no-any-return]

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self.max_retries:
                    raise MetaPublishingError(f"Network error contacting Meta API: {exc}") from exc
                LOGGER.warning("Network error on Meta request. Retrying in %.1fs...", backoff)
                await asyncio.sleep(backoff)
                backoff *= 2

        raise MetaPublishingError("Exhausted retries calling Meta Graph API.")

    def _resolve_access_token(self) -> str:
        token = (
            self.settings.meta_access_token.get_secret_value()
            if self.settings.meta_access_token
            else None
        )
        if not token:
            raise MetaPublishingError("META_ACCESS_TOKEN is not configured in settings.")
        return token

    # ---------------------------------------------------------------------------
    # Facebook Page Publishing
    # ---------------------------------------------------------------------------

    async def publish_facebook(
        self,
        media_path: Path | str,
        caption: str,
        is_video: bool = False,
    ) -> PublishResult:
        """Publish a photo or video/reel to a Facebook Page."""
        page_id = self.settings.meta_page_id
        if not page_id:
            raise MetaPublishingError("META_PAGE_ID is not configured in settings.")

        access_token = self._resolve_access_token()
        path = Path(media_path)
        if not path.exists():
            raise FileNotFoundError(f"Media file not found at {path}")

        headers = {"Authorization": f"Bearer {access_token}"}

        if is_video:
            url = f"{self.base_url}/{page_id}/videos"
            with path.open("rb") as f:
                files = {"source": (path.name, f, "video/mp4")}
                data = {"description": caption}
                res = await self._request_with_retry(
                    "POST", url, data=data, files=files, headers=headers
                )
            post_id = str(res.get("id"))
            permalink = f"https://www.facebook.com/{page_id}/videos/{post_id}"
        else:
            url = f"{self.base_url}/{page_id}/photos"
            with path.open("rb") as f:
                files = {"source": (path.name, f, "image/png")}
                data = {"caption": caption}
                res = await self._request_with_retry(
                    "POST", url, data=data, files=files, headers=headers
                )
            post_id = str(res.get("post_id") or res.get("id"))
            permalink = f"https://www.facebook.com/{post_id}"

        return PublishResult(
            platform="facebook",
            external_post_id=post_id,
            permalink=permalink,
            published_at=datetime.now(UTC),
            metadata={"page_id": page_id, "is_video": is_video},
        )

    # ---------------------------------------------------------------------------
    # Instagram Business Publishing (Container -> Status Poll -> Publish)
    # ---------------------------------------------------------------------------

    async def publish_instagram(
        self,
        media_url: str,
        caption: str,
        is_video: bool = False,
        poll_interval_seconds: float = 2.0,
        max_poll_attempts: int = 15,
    ) -> PublishResult:
        """Publish an image or reel to an Instagram Business account via container lifecycle."""
        ig_user_id = self.settings.meta_instagram_account_id
        if not ig_user_id:
            raise MetaPublishingError("META_INSTAGRAM_ACCOUNT_ID is not configured in settings.")

        access_token = self._resolve_access_token()
        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 1: Create Media Container
        container_url = f"{self.base_url}/{ig_user_id}/media"
        if is_video:
            container_data = {
                "media_type": "REELS",
                "video_url": media_url,
                "caption": caption,
                "share_to_feed": "true",
            }
        else:
            container_data = {
                "image_url": media_url,
                "caption": caption,
            }

        create_res = await self._request_with_retry(
            "POST", container_url, data=container_data, headers=headers
        )
        container_id = str(create_res["id"])
        LOGGER.info("Created Instagram container %s (is_video=%s)", container_id, is_video)

        # Step 2: Poll Container Status
        status_url = f"{self.base_url}/{container_id}"
        poll_attempts = 0
        while poll_attempts < max_poll_attempts:
            status_res = await self._request_with_retry(
                "GET", status_url, params={"fields": "status_code"}, headers=headers
            )
            status_code = status_res.get("status_code", "").upper()
            LOGGER.debug("Instagram container %s status: %s", container_id, status_code)

            if status_code == "FINISHED":
                break
            if status_code in ("ERROR", "EXPIRED"):
                raise MetaContainerProcessingError(
                    f"Instagram container {container_id} failed with status: {status_code}"
                )

            poll_attempts += 1
            await asyncio.sleep(poll_interval_seconds)

        # Step 3: Publish Container
        publish_url = f"{self.base_url}/{ig_user_id}/media_publish"
        publish_res = await self._request_with_retry(
            "POST", publish_url, data={"creation_id": container_id}, headers=headers
        )
        media_id = str(publish_res["id"])
        LOGGER.info("Published Instagram media %s", media_id)

        # Step 4: Retrieve Permalink
        permalink: str | None = None
        try:
            media_info_url = f"{self.base_url}/{media_id}"
            info_res = await self._request_with_retry(
                "GET", media_info_url, params={"fields": "permalink"}, headers=headers
            )
            permalink = info_res.get("permalink")
        except Exception as exc:
            LOGGER.warning("Could not fetch IG permalink for %s: %s", media_id, exc)
            permalink = f"https://www.instagram.com/p/{media_id}"

        return PublishResult(
            platform="instagram",
            external_post_id=media_id,
            permalink=permalink,
            published_at=datetime.now(UTC),
            metadata={"ig_user_id": ig_user_id, "container_id": container_id},
        )
