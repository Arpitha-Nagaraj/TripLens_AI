from __future__ import annotations

from typing import Any, TypedDict

from travelgpt.browser_client import BrowserMCPClient, BrowserMCPClientProtocol
from travelgpt.travel_parser import HotelResult, TravelParser


class TravelSearchResponse(TypedDict):
    query: str
    category: str
    count: int
    results: list[HotelResult]


class TravelAgent:
    """
    Coordinate browser searches and parsing.

    Flow:
        User query
            -> BrowserMCPClient
            -> Playwright accessibility snapshot
            -> TravelParser
            -> Structured hotel results
    """

    def __init__(
        self,
        browser_client: BrowserMCPClientProtocol | None = None,
    ) -> None:
        self.browser_client = browser_client or BrowserMCPClient()

    def search(
        self,
        query: str,
        category: str,
        *,
        destination: str = "",
        limit: int | None = 5,
    ) -> TravelSearchResponse:
        """
        Search for travel results and return structured data.

        Currently supported category:
            - hotels
        """
        normalized_query = query.strip()
        normalized_category = category.strip().lower()

        if not normalized_query:
            raise ValueError("Search query cannot be empty.")

        if not normalized_category:
            raise ValueError("Search category cannot be empty.")

        browser_results = self.browser_client.search(
            query=normalized_query,
            category=normalized_category,
        )

        structured_results = self._parse_browser_results(
            browser_results=browser_results,
            category=normalized_category,
            destination=destination,
            limit=limit,
        )

        return TravelSearchResponse(
            query=normalized_query,
            category=normalized_category,
            count=len(structured_results),
            results=structured_results,
        )

    @staticmethod
    def _parse_browser_results(
        browser_results: list[dict[str, Any]],
        category: str,
        destination: str,
        limit: int | None,
    ) -> list[HotelResult]:
        if category != "hotels":
            raise ValueError(
                f"Unsupported travel category: {category}. "
                "Currently, only 'hotels' is supported."
            )

        hotels: list[HotelResult] = []
        seen: set[tuple[str, str]] = set()

        for browser_result in browser_results:
            snapshot = browser_result.get("snapshot", "")

            if not isinstance(snapshot, str) or not snapshot.strip():
                continue

            parsed_hotels = TravelParser.parse_hotels(
                snapshot,
                destination=destination,
            )

            for hotel in parsed_hotels:
                identity = (
                    hotel["name"].casefold(),
                    hotel["price"],
                )

                if identity in seen:
                    continue

                seen.add(identity)
                hotels.append(hotel)

                if limit is not None and len(hotels) >= limit:
                    return hotels

        return hotels