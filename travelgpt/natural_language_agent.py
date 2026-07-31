from __future__ import annotations

from typing import TypedDict

from travelgpt.request_parser import (
    GeminiRequestParser,
    TravelSearchRequest,
)
from travelgpt.travel_agent import TravelAgent, TravelSearchResponse


class NaturalLanguageTravelResponse(TypedDict):
    original_request: str
    interpreted_request: dict[str, object]
    search_response: TravelSearchResponse


class NaturalLanguageTravelAgent:
    """
    Accept natural-language travel requests and run structured searches.

    Flow:
        User request
            -> GeminiRequestParser
            -> TravelAgent
            -> BrowserMCPClient
            -> TravelParser
            -> Structured results
    """

    def __init__(
        self,
        request_parser: GeminiRequestParser | None = None,
        travel_agent: TravelAgent | None = None,
    ) -> None:
        self.request_parser = request_parser or GeminiRequestParser()
        self.travel_agent = travel_agent or TravelAgent()

    def search(
        self,
        user_request: str,
    ) -> NaturalLanguageTravelResponse:
        normalized_request = user_request.strip()

        if not normalized_request:
            raise ValueError("Travel request cannot be empty.")

        parsed_request = self.request_parser.parse(normalized_request)

        search_response = self._execute_search(parsed_request)

        return NaturalLanguageTravelResponse(
            original_request=normalized_request,
            interpreted_request=parsed_request.model_dump(),
            search_response=search_response,
        )

    def _execute_search(
        self,
        parsed_request: TravelSearchRequest,
    ) -> TravelSearchResponse:
        return self.travel_agent.search(
            query=parsed_request.query,
            category=parsed_request.category,
            destination=parsed_request.destination,
            limit=parsed_request.limit,
        )