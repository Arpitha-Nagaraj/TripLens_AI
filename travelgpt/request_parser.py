from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError


load_dotenv()


class TravelSearchRequest(BaseModel):
    """Structured search parameters extracted from a user request."""

    query: str = Field(
        description=(
            "A browser-ready travel search query. "
            "Example: affordable hotels in San Francisco"
        )
    )

    category: Literal["hotels"] = Field(
        description="The travel category requested by the user."
    )

    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of results requested by the user.",
    )

    destination: str = Field(
        description="The city, region, or destination in the request."
    )

    price_preference: Literal[
        "budget",
        "affordable",
        "moderate",
        "luxury",
        "unspecified",
    ] = Field(
        default="unspecified",
        description="The user's stated price preference.",
    )


class GeminiRequestParser:
    """Convert natural-language travel requests into structured parameters."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        resolved_api_key = api_key or os.getenv("GEMINI_API_KEY")

        if not resolved_api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. "
                "Add it to your .env file."
            )

        self.client = genai.Client(api_key=resolved_api_key)
        self.model = model or os.getenv(
            "GEMINI_MODEL",
            "gemini-2.5-flash",
        )

    def parse(self, user_request: str) -> TravelSearchRequest:
        """
        Convert a natural-language request into travel search parameters.

        Example:
            "Find me five affordable hotels in San Francisco"

        Returns:
            TravelSearchRequest(
                query="affordable hotels in San Francisco",
                category="hotels",
                limit=5,
                destination="San Francisco",
                price_preference="affordable",
            )
        """
        normalized_request = user_request.strip()

        if not normalized_request:
            raise ValueError("Travel request cannot be empty.")

        prompt = f"""
You are the request-understanding component of a travel search agent.

Convert the user's request into structured hotel-search parameters.

Rules:
1. The only currently supported category is "hotels".
2. Extract the destination exactly and clearly.
3. Extract the requested result count.
4. If no count is provided, use 5.
5. The limit must be between 1 and 20.
6. Detect a price preference:
   - "cheap" or "budget" means "budget"
   - "affordable" means "affordable"
   - "moderately priced" or similar means "moderate"
   - "luxury" or "high-end" means "luxury"
   - otherwise use "unspecified"
7. Build a concise Google-search-ready query.
8. Do not include phrases such as "find me", "show me", or
   "can you search".
9. Do not invent dates, guest counts, amenities, or destinations.

User request:
{normalized_request}
""".strip()

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=TravelSearchRequest,
            ),
        )

        if response.parsed is not None:
            if isinstance(response.parsed, TravelSearchRequest):
                return response.parsed

            return TravelSearchRequest.model_validate(response.parsed)

        if not response.text:
            raise RuntimeError(
                "Gemini returned an empty response while parsing "
                "the travel request."
            )

        try:
            return TravelSearchRequest.model_validate_json(response.text)
        except ValidationError as error:
            raise RuntimeError(
                "Gemini returned an invalid travel search request."
            ) from error