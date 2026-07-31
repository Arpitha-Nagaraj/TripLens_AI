from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Protocol
from urllib.parse import quote_plus, urljoin

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class BrowserMCPClientProtocol(Protocol):
    def search(
        self,
        query: str,
        category: str,
    ) -> list[dict[str, Any]]:
        """Execute a browser-based search for the requested category."""


class BrowserMCPClient:
    """
    Reusable Playwright MCP client for browser-based travel searches.

    Hotel flow:
        Google Search
            -> detect Google Travel "See more" link
            -> navigate to dedicated Google Travel results
            -> scroll results
            -> extract hotel cards from the rendered DOM
            -> capture accessibility snapshots as a fallback/debug source
    """

    GOOGLE_BASE_URL = "https://www.google.com"
    RICH_RESULTS_MARKER = "TRAVELGPT_RICH_HOTELS_JSON:"

    _SEE_MORE_PATTERN = re.compile(
        r'- link "See more" '
        r'\[ref=[^\]]+\](?: \[cursor=pointer\])?:\s*'
        r'\n\s+- /url: (?P<url>"[^"]*"|\S+)',
        re.MULTILINE,
    )

    def __init__(
        self,
        server_command: str | None = None,
        server_args: list[str] | None = None,
    ) -> None:
        self.server_command = server_command or "npx"
        self.server_args = server_args or [
            "-y",
            "@playwright/mcp@latest",
        ]

    def search(
        self,
        query: str,
        category: str,
    ) -> list[dict[str, Any]]:
        """Execute a synchronous browser search."""
        normalized_query = query.strip()
        normalized_category = category.strip().lower()

        if not normalized_query:
            raise ValueError("Search query cannot be empty.")

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self._search_async(
                    query=normalized_query,
                    category=normalized_category,
                )
            )

        raise RuntimeError(
            "BrowserMCPClient.search() cannot be called from an active "
            "async event loop. Use await search_async() instead."
        )

    async def search_async(
        self,
        query: str,
        category: str,
    ) -> list[dict[str, Any]]:
        """Execute an asynchronous browser search."""
        normalized_query = query.strip()
        normalized_category = category.strip().lower()

        if not normalized_query:
            raise ValueError("Search query cannot be empty.")

        return await self._search_async(
            query=normalized_query,
            category=normalized_category,
        )

    async def _search_async(
        self,
        query: str,
        category: str,
    ) -> list[dict[str, Any]]:
        search_url = self._build_search_url(
            query=query,
            category=category,
        )

        server_params = StdioServerParameters(
            command=self.server_command,
            args=self.server_args,
        )

        logger.info(
            "Starting Playwright MCP search: query=%r category=%r",
            query,
            category,
        )

        try:
            async with stdio_client(server_params) as (
                read_stream,
                write_stream,
            ):
                async with ClientSession(
                    read_stream,
                    write_stream,
                ) as session:
                    await session.initialize()

                    await self.navigate(session=session, url=search_url)
                    await self.wait_for(session=session, time=3)

                    initial_snapshot = await self.snapshot(
                        session=session,
                        depth=8,
                    )

                    final_url = search_url

                    if category in {"hotel", "hotels"}:
                        google_travel_url = self._extract_google_travel_url(
                            initial_snapshot
                        )

                        if google_travel_url:
                            logger.info(
                                "Opening dedicated Google Travel page: %s",
                                google_travel_url,
                            )
                            await self.navigate(
                                session=session,
                                url=google_travel_url,
                            )
                            await self.wait_for(session=session, time=4)
                            final_url = google_travel_url
                        else:
                            logger.info(
                                "No Google Travel 'See more' link found. "
                                "Continuing with the current search page."
                            )

                    snapshot_text = await self._collect_scrolled_snapshots(
                        session=session,
                        scroll_count=3,
                        wait_seconds=1.5,
                        snapshot_depth=10,
                    )

                    rich_hotels: list[dict[str, Any]] = []

                    if category in {"hotel", "hotels"}:
                        rich_hotels = await self._extract_rendered_hotels(
                            session=session
                        )

                    if rich_hotels:
                        snapshot_text = (
                            f"{self.RICH_RESULTS_MARKER}"
                            f"{json.dumps(rich_hotels, ensure_ascii=False)}"
                            f"\n\n{snapshot_text}"
                        )

                    with open(
                        "last_snapshot.txt",
                        "w",
                        encoding="utf-8",
                    ) as output_file:
                        output_file.write(snapshot_text)

                    return [
                        {
                            "query": query,
                            "category": category,
                            "url": final_url,
                            "snapshot": snapshot_text,
                            "rich_results": rich_hotels,
                        }
                    ]

        except Exception:
            logger.exception(
                "Playwright MCP search failed: query=%r category=%r",
                query,
                category,
            )
            raise

    async def _extract_rendered_hotels(
        self,
        session: ClientSession,
    ) -> list[dict[str, Any]]:
        """
        Extract rich hotel data from the rendered Google Travel DOM.

        Google uses generated CSS class names, so extraction is anchored on
        hotel links whose URLs contain `/travel/search` and `qs=`. The script
        then walks up the DOM to find the smallest useful card container and
        parses its visible text, images, prices, ratings, reviews, and amenities.
        """
        extraction_script = r"""
() => {
  const unique = (items) => [...new Set(items.filter(Boolean))];
  const clean = (value) => (value || "").replace(/\s+/g, " ").trim();

  const pricePattern = /(?:US\$|\$)\s?\d[\d,]*(?:\.\d{1,2})?/i;

  const ratingPatterns = [
    /(\d(?:\.\d+)?)\s+out of\s+5(?:\s+stars?)?/i,
    /(\d(?:\.\d+)?)\s*\/\s*5/i,
    /\brated\s+([1-5](?:\.\d+)?)\b/i,
    /\b([1-5](?:\.\d+)?)\s+stars?\b/i,
    /\b([1-5](?:\.\d+)?)\s*\(\s*[\d,.]+\s*(?:reviews?)?\s*\)/i,
    /\b([1-5](?:\.\d+)?)\s*[·•|]\s*[\d,.]+\s+reviews?\b/i,
    /\b([1-5](?:\.\d+)?)\b(?=.{0,35}\breviews?\b)/i,
  ];

  const reviewPatterns = [
    /(?:from\s+)?([\d,.]+\s*[KM]?)\s+(?:Google\s+)?reviews?/i,
    /\(([\d,.]+\s*[KM]?)\s*(?:reviews?)?\)/i,
  ];

  const amenityNames = [
    "Free Wi-Fi", "Free breakfast", "Free parking", "Pool", "Hot tub",
    "Air conditioning", "Restaurant", "Bar", "Spa", "Fitness center",
    "Airport shuttle", "Pet-friendly", "Beach access", "Room service",
    "Kitchen", "Washer", "Accessible", "Smoke-free", "Business center",
    "Full-service laundry"
  ];

  const normalizeName = (value) => {
    let name = clean(value);

    name = name.replace(
      /^(?:view prices?|photos?|reviews?|details?) for\s+/i,
      ""
    );

    name = name.replace(
      /^prices? starting from\s+(?:US\$|\$)\s?\d[\d,]*(?:\.\d{1,2})?\s*,?\s*/i,
      ""
    );

    const ratingPrefix = name.match(
      /^\d(?:\.\d+)?\s+out of 5 stars?\s+from\s+[\d,.]+\s+reviews?\s*,\s*(.+)$/i
    );
    if (ratingPrefix) {
      name = clean(ratingPrefix[1]);
    }

    name = name
      .replace(/\s+(?:GREAT DEAL|GOOD DEAL|DEAL)\b.*$/i, "")
      .replace(/\s+\d+%\s+less than usual.*$/i, "");

    return clean(name).replace(/^[,\s-]+|[,\s-]+$/g, "");
  };

  const extractRating = (text) => {
    for (const pattern of ratingPatterns) {
      const match = text.match(pattern);
      if (!match) continue;

      const value = Number.parseFloat(match[1]);
      if (Number.isFinite(value) && value >= 0 && value <= 5) {
        return value;
      }
    }
    return null;
  };

  const extractReviews = (text) => {
    for (const pattern of reviewPatterns) {
      const match = text.match(pattern);
      if (!match) continue;

      let raw = match[1].replace(/,/g, "").trim().toLowerCase();
      let multiplier = 1;

      if (raw.endsWith("k")) {
        multiplier = 1000;
        raw = raw.slice(0, -1);
      } else if (raw.endsWith("m")) {
        multiplier = 1000000;
        raw = raw.slice(0, -1);
      }

      const value = Number.parseFloat(raw);
      if (Number.isFinite(value)) {
        return Math.round(value * multiplier);
      }
    }
    return null;
  };

  const allTravelAnchors = [
    ...document.querySelectorAll('a[href*="/travel/search"]')
  ].filter((anchor) => anchor.href.includes("qs="));

  const candidatesByHotel = new Map();

  for (const anchor of allTravelAnchors) {
    const rawLabel = clean(
      anchor.getAttribute("aria-label")
      || anchor.innerText
      || anchor.textContent
    );

    const hotelName = normalizeName(rawLabel);
    if (!hotelName || hotelName.length < 3 || hotelName.length > 120) {
      continue;
    }

    const key = hotelName.toLowerCase();
    if (!candidatesByHotel.has(key)) {
      candidatesByHotel.set(key, {
        name: hotelName,
        anchors: [],
      });
    }

    candidatesByHotel.get(key).anchors.push(anchor);
  }

  const hotels = [];

  for (const { name, anchors } of candidatesByHotel.values()) {
    const textParts = [];
    const imageCandidates = [];
    let bestLink = anchors[0]?.href || null;

    for (const anchor of anchors) {
      textParts.push(
        clean(anchor.getAttribute("aria-label")),
        clean(anchor.getAttribute("title")),
        clean(anchor.innerText),
        clean(anchor.textContent)
      );

      let node = anchor;

      for (let depth = 0; depth < 8 && node; depth += 1) {
        const visibleText = clean(node.innerText);
        if (visibleText) {
          textParts.push(visibleText);
        }

        const labelledElements = node.querySelectorAll(
          "[aria-label], [title]"
        );

        for (const element of labelledElements) {
          textParts.push(
            clean(element.getAttribute("aria-label")),
            clean(element.getAttribute("title"))
          );
        }

        for (const image of node.querySelectorAll("img[src]")) {
          const imageUrl = image.currentSrc || image.src;
          if (imageUrl) {
            imageCandidates.push(imageUrl);
          }
        }

        const distinctHotelLinks = unique(
          [...node.querySelectorAll('a[href*="/travel/search"][href*="qs="]')]
            .map((link) => normalizeName(
              link.getAttribute("aria-label")
              || link.innerText
              || link.textContent
            ))
            .filter(Boolean)
            .map((hotel) => hotel.toLowerCase())
        );

        // Stop before climbing into a parent containing multiple properties.
        if (distinctHotelLinks.length > 1) {
          break;
        }

        node = node.parentElement;
      }
    }

    const searchableText = unique(textParts).join(" | ");
    const rating = extractRating(searchableText);
    const reviews = extractReviews(searchableText);

    const priceMatch = searchableText.match(pricePattern);
    const price = priceMatch
      ? clean(priceMatch[0].replace(/^US\$/i, "$"))
      : null;

    const amenities = amenityNames.filter((amenity) =>
      searchableText.toLowerCase().includes(amenity.toLowerCase())
    );

    const descriptionCandidates = unique(textParts)
      .filter((line) => line && line.toLowerCase() !== name.toLowerCase())
      .filter((line) => !pricePattern.test(line))
      .filter((line) => !/reviews?|out of 5|stars?/i.test(line))
      .filter((line) => !/view|select|book|deal|price|night|tax|fees?|photos? for/i.test(line))
      .filter((line) => line.length >= 12 && line.length <= 240);

    const description = descriptionCandidates[0] || null;

    hotels.push({
      name,
      price,
      rating,
      reviews,
      description,
      amenities: unique(amenities),
      image: imageCandidates[0] || null,
      link: bestLink,
      raw_text: searchableText,
    });
  }

  return hotels;
}
"""

        try:
            raw_result = await self.evaluate(
                session=session,
                function=extraction_script,
            )
            return self._decode_evaluation_result(raw_result)
        except Exception:
            logger.exception(
                "Rich hotel DOM extraction failed; using snapshot fallback."
            )
            return []

    @staticmethod
    def _decode_evaluation_result(raw_result: str) -> list[dict[str, Any]]:
        """Decode JSON returned by Playwright MCP's browser_evaluate tool."""
        if not raw_result.strip():
            return []

        candidates = [raw_result.strip()]

        fenced_match = re.search(
            r"```(?:json)?\s*(\[.*\])\s*```",
            raw_result,
            re.DOTALL,
        )
        if fenced_match:
            candidates.insert(0, fenced_match.group(1))

        array_match = re.search(r"(\[\s*\{.*\}\s*\])", raw_result, re.DOTALL)
        if array_match:
            candidates.insert(0, array_match.group(1))

        for candidate in candidates:
            try:
                decoded = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if isinstance(decoded, list):
                return [item for item in decoded if isinstance(item, dict)]

        logger.warning("Could not decode browser_evaluate hotel payload: %s", raw_result[:500])
        return []

    async def _collect_scrolled_snapshots(
        self,
        session: ClientSession,
        *,
        scroll_count: int = 3,
        wait_seconds: float = 1.5,
        snapshot_depth: int = 10,
    ) -> str:
        """Capture the current snapshot and snapshots after scrolling."""
        snapshots: list[str] = []

        initial_snapshot = await self.snapshot(
            session=session,
            depth=snapshot_depth,
        )
        if initial_snapshot:
            snapshots.append(initial_snapshot)

        for scroll_number in range(1, scroll_count + 1):
            logger.info(
                "Scrolling results: step=%d of %d",
                scroll_number,
                scroll_count,
            )
            await self.press_key(session=session, key="PageDown")
            await self.wait_for(session=session, time=wait_seconds)

            scrolled_snapshot = await self.snapshot(
                session=session,
                depth=snapshot_depth,
            )
            if scrolled_snapshot:
                snapshots.append(scrolled_snapshot)

        return "\n\n".join(
            f"--- SNAPSHOT {index} ---\n{snapshot}"
            for index, snapshot in enumerate(snapshots, start=1)
        )

    @classmethod
    def _extract_google_travel_url(cls, snapshot: str) -> str | None:
        """Extract the hotel widget's Google Travel 'See more' URL."""
        match = cls._SEE_MORE_PATTERN.search(snapshot)
        if match is None:
            return None

        raw_url = match.group("url").strip('"')
        if not raw_url or raw_url == "#":
            return None

        return urljoin(cls.GOOGLE_BASE_URL, raw_url)

    async def navigate(self, session: ClientSession, url: str) -> str:
        return await self._call_tool(
            session=session,
            tool_name="browser_navigate",
            arguments={"url": url},
        )

    async def press_key(self, session: ClientSession, key: str) -> str:
        return await self._call_tool(
            session=session,
            tool_name="browser_press_key",
            arguments={"key": key},
        )

    async def wait_for(
        self,
        session: ClientSession,
        *,
        time: float | None = None,
        text: str | None = None,
        text_gone: str | None = None,
    ) -> str:
        arguments: dict[str, Any] = {}
        if time is not None:
            arguments["time"] = time
        if text is not None:
            arguments["text"] = text
        if text_gone is not None:
            arguments["textGone"] = text_gone
        if not arguments:
            raise ValueError("wait_for() requires time, text, or text_gone.")

        return await self._call_tool(
            session=session,
            tool_name="browser_wait_for",
            arguments=arguments,
        )

    async def snapshot(
        self,
        session: ClientSession,
        *,
        target: str | None = None,
        filename: str | None = None,
        depth: int | None = None,
        boxes: bool = False,
    ) -> str:
        arguments: dict[str, Any] = {"boxes": boxes}
        if target:
            arguments["target"] = target
        if filename:
            arguments["filename"] = filename
        if depth is not None:
            arguments["depth"] = depth

        return await self._call_tool(
            session=session,
            tool_name="browser_snapshot",
            arguments=arguments,
        )

    async def evaluate(
        self,
        session: ClientSession,
        function: str,
    ) -> str:
        """Evaluate JavaScript in the current browser page."""
        if not function.strip():
            raise ValueError("Evaluation function cannot be empty.")

        return await self._call_tool(
            session=session,
            tool_name="browser_evaluate",
            arguments={"function": function},
        )

    async def _call_tool(
        self,
        session: ClientSession,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> str:
        logger.debug(
            "Calling Playwright MCP tool %s with arguments %s",
            tool_name,
            arguments,
        )

        result = await session.call_tool(tool_name, arguments=arguments)

        if getattr(result, "isError", False):
            error_message = self._extract_text_content(result)
            raise RuntimeError(
                f"Playwright MCP tool {tool_name!r} failed: "
                f"{error_message or 'Unknown error'}"
            )

        return self._extract_text_content(result)

    @staticmethod
    def _extract_text_content(result: Any) -> str:
        content_items = getattr(result, "content", None) or []
        text_parts: list[str] = []

        for item in content_items:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                text_parts.append(text)

        return "\n".join(text_parts).strip()

    @staticmethod
    def _build_search_url(query: str, category: str) -> str:
        normalized_query = query.strip()
        normalized_category = category.strip()

        if (
            normalized_category
            and normalized_category.casefold() not in normalized_query.casefold()
        ):
            search_terms = f"{normalized_query} {normalized_category}"
        else:
            search_terms = normalized_query

        return "https://www.google.com/search?q=" f"{quote_plus(search_terms)}"