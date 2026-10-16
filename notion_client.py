"""Notion queries with bounded rate-limit retries and complete pagination."""

import logging
import math
import time

import requests
from notion import Query as BaseQuery


class Query(BaseQuery):
    def set_token(self, token):
        super().set_token(token)
        self._headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    def _request(self, method, url, **kwargs):
        for attempt in range(6):
            response = requests.request(
                method, url, headers=self._headers, timeout=60, **kwargs
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code != 429 or attempt == 5:
                raise RuntimeError(
                    f"Notion API {method} {url} failed: "
                    f"{response.status_code} {response.text}"
                )
            delay = response.headers.get("Retry-After")
            if delay is None:
                try:
                    delay = response.json().get("additional_data", {}).get("retry_after")
                except (ValueError, AttributeError):
                    delay = None
            try:
                delay = float(delay)
                if not math.isfinite(delay) or delay < 0:
                    raise ValueError("Invalid retry delay")
            except (TypeError, ValueError):
                delay = 2 ** attempt
            delay = max(1, delay)
            logging.warning(
                "Notion API rate limited; retry %s/5 in %s seconds", attempt + 1, delay
            )
            # The workflow also captures stdout, unlike the in-memory WebDAV log.
            print(f"Notion API rate limited; retry {attempt + 1}/5 in {delay:g} seconds", flush=True)
            time.sleep(delay)

    def get_pages(self, num_pages=None, database_id=None, filters=None):
        database_id = database_id or self.DATABASE_ID
        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        payload = {"page_size": 100}
        results = []
        while True:
            data = self._request("POST", url, json=payload)
            results.extend(
                page for page in data["results"]
                if not filters or self.is_page_selected(page, filters)
            )
            if num_pages is not None and len(results) >= num_pages:
                return results[:num_pages]
            if not data.get("has_more"):
                return results
            payload["start_cursor"] = data["next_cursor"]

    def get_blocks(self, page_id=None, filters=None):
        page_id = page_id or self.PAGE_ID
        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        params = {"page_size": 100}
        results = []
        while True:
            data = self._request("GET", url, params=params)
            results.extend(
                block for block in data["results"]
                if not filters or self.is_block_selected(block, filters)
            )
            if not data.get("has_more"):
                return results
            params["start_cursor"] = data["next_cursor"]
