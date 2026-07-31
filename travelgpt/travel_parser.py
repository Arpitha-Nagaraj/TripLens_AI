from __future__ import annotations

import json
import re
from typing import Any, TypedDict
from urllib.parse import quote_plus, urljoin


class HotelResult(TypedDict):
    name: str
    price: str
    rating: float | None
    reviews: int | None
    description: str
    location_highlight: str | None
    property_highlights: list[str]
    guest_mentions: list[str]
    amenities: list[str]
    image: str | None
    link: str


class TravelParser:
    """Parse and merge hotel results from Google Travel snapshots."""

    GOOGLE_BASE_URL = "https://www.google.com"
    GOOGLE_TRAVEL_URL = "https://www.google.com/travel/search"
    RICH_RESULTS_MARKER = "TRAVELGPT_RICH_HOTELS_JSON:"

    _LINK_PATTERN = re.compile(
        r'- link "(?P<label>.+?)" '
        r'\[ref=[^\]]+\](?: \[cursor=pointer\])?:\s*'
        r'\n\s+- /url: (?P<url>"[^"]*"|\S+)',
        re.MULTILINE,
    )

    _AMENITIES = (
        "Free Wi-Fi",
        "Free breakfast",
        "Free parking",
        "Pool",
        "Hot tub",
        "Air conditioning",
        "Restaurant",
        "Bar",
        "Spa",
        "Fitness center",
        "Airport shuttle",
        "Pet-friendly",
        "Beach access",
        "Room service",
        "Kitchen",
        "Washer",
        "Accessible",
        "Smoke-free",
        "Business center",
    )

    _NON_HOTEL_LABELS = {
        "google",
        "explore",
        "flights",
        "hotels",
        "vacation rentals",
        "holiday rentals",
        "see more",
        "view larger map",
        "sign in",
        "learn more",
        "privacy",
        "terms",
        "feedback",
        "help center",
        "about",
    }

    _INVALID_NAMES = re.compile(
        r"^(?:great deal|good deal|deal|excellent location|good location|"
        r"location|rating|reviews?|see availability|book|learn more|"
        r"open google travel|price shown|photos?)$",
        re.IGNORECASE,
    )

    @classmethod
    def parse_hotels(
        cls,
        snapshot: str,
        *,
        destination: str = "",
        limit: int | None = None,
    ) -> list[HotelResult]:
        """
        Parse hotels and merge all links belonging to the same property.

        Google Travel commonly exposes multiple links per hotel:
        price/deal, rating/reviews, photos, and "view prices". These are
        normalized to one hotel name before the result limit is applied.
        """
        if not snapshot.strip():
            return []

        hotels_by_name: dict[str, HotelResult] = {}

        for hotel in cls._parse_rich_results(snapshot, destination):
            cls._merge_hotel(hotels_by_name, hotel)

        for match in cls._LINK_PATTERN.finditer(snapshot):
            label = cls._unescape_snapshot_text(match.group("label"))
            raw_url = match.group("url").strip('"')

            hotel = cls._parse_snapshot_link(
                label=label,
                raw_url=raw_url,
                destination=destination,
            )
            if hotel is not None:
                cls._merge_hotel(hotels_by_name, hotel)

        hotels = list(hotels_by_name.values())
        if limit is not None:
            hotels = hotels[:limit]
        return hotels

    @classmethod
    def _parse_rich_results(
        cls,
        snapshot: str,
        destination: str,
    ) -> list[HotelResult]:
        marker_position = snapshot.find(cls.RICH_RESULTS_MARKER)
        if marker_position < 0:
            return []

        json_start = marker_position + len(cls.RICH_RESULTS_MARKER)
        json_line = snapshot[json_start:].splitlines()[0].strip()

        try:
            payload = json.loads(json_line)
        except json.JSONDecodeError:
            return []

        if not isinstance(payload, list):
            return []

        results: list[HotelResult] = []

        for item in payload:
            if not isinstance(item, dict):
                continue

            raw_text = cls._clean_text(item.get("raw_text"))
            name = cls._normalize_hotel_name(item.get("name"))
            if not cls._is_valid_hotel_name(name):
                continue

            price = cls._normalize_price(item.get("price"))
            rating = cls._coerce_rating(item.get("rating"))
            reviews = cls._coerce_reviews(item.get("reviews"))

            price = price or cls._extract_price(raw_text)
            rating = rating if rating is not None else cls._extract_rating(raw_text)
            reviews = reviews if reviews is not None else cls._extract_reviews(raw_text)

            amenities = cls._normalize_amenities(item.get("amenities"), raw_text)
            description = cls._clean_text(item.get("description"))

            structured_text = " | ".join(
                part
                for part in (raw_text, description)
                if part
            )
            location_highlight = cls._extract_location_highlight(structured_text)
            guest_mentions = cls._extract_guest_mentions(structured_text)
            property_highlights = cls._extract_property_highlights(
                structured_text,
                amenities=amenities,
                location_highlight=location_highlight,
                guest_mentions=guest_mentions,
            )

            link = cls._normalize_url(cls._clean_text(item.get("link")))
            image = cls._clean_text(item.get("image")) or None

            results.append(
                HotelResult(
                    name=name,
                    price=price or "See live price",
                    rating=rating,
                    reviews=reviews,
                    description=(
                        ""
                        if re.search(
                            r"54321|People often mention|out of 5|reviews?",
                            description,
                            re.I,
                        )
                        else description
                    ),
                    location_highlight=location_highlight,
                    property_highlights=property_highlights,
                    guest_mentions=guest_mentions,
                    amenities=amenities,
                    image=image,
                    link=link or cls._build_hotel_link(name, destination),
                )
            )

        return results

    @classmethod
    def _parse_snapshot_link(
        cls,
        *,
        label: str,
        raw_url: str,
        destination: str,
    ) -> HotelResult | None:
        if not label or not raw_url:
            return None

        absolute_url = cls._normalize_url(raw_url)
        if "/travel/search" not in absolute_url:
            return None

        normalized_label = cls._clean_text(label)
        if normalized_label.casefold() in cls._NON_HOTEL_LABELS:
            return None

        name = cls._normalize_hotel_name(normalized_label)
        if not cls._is_valid_hotel_name(name):
            return None

        amenities = cls._extract_amenities(normalized_label)
        location_highlight = cls._extract_location_highlight(normalized_label)
        guest_mentions = cls._extract_guest_mentions(normalized_label)
        property_highlights = cls._extract_property_highlights(
            normalized_label,
            amenities=amenities,
            location_highlight=location_highlight,
            guest_mentions=guest_mentions,
        )

        return HotelResult(
            name=name,
            price=cls._extract_price(normalized_label) or "See live price",
            rating=cls._extract_rating(normalized_label),
            reviews=cls._extract_reviews(normalized_label),
            description="Open Google Travel to view current property details.",
            location_highlight=location_highlight,
            property_highlights=property_highlights,
            guest_mentions=guest_mentions,
            amenities=amenities,
            image=None,
            link=absolute_url or cls._build_hotel_link(name, destination),
        )

    @classmethod
    def _normalize_hotel_name(cls, value: Any) -> str:
        name = cls._clean_text(value)
        if not name:
            return ""

        # Auxiliary links belonging to one property.
        name = re.sub(
            r"^(?:view prices?|photos?|reviews?|details?) for\s+",
            "",
            name,
            flags=re.I,
        )

        # Price/deal link:
        # "Prices starting from $71, San Remo Hotel GREAT DEAL 36% less..."
        name = re.sub(
            r"^prices? starting from\s+(?:US\$|\$)\s?\d[\d,]*(?:\.\d{1,2})?\s*,?\s*",
            "",
            name,
            flags=re.I,
        )

        # Rating link:
        # "4.3 out of 5 stars from 978 reviews, San Remo Hotel"
        rating_prefix = re.match(
            r"^\d(?:\.\d+)?\s+out of 5 stars?\s+from\s+"
            r"[\d,.]+\s+reviews?\s*,\s*(.+)$",
            name,
            flags=re.I,
        )
        if rating_prefix:
            name = rating_prefix.group(1)

        # Generic review prefix ending in a comma.
        review_suffix = re.search(r"reviews?\s*,\s*(.+)$", name, re.I)
        if review_suffix:
            name = review_suffix.group(1)

        # Remove deal and price suffixes.
        name = re.sub(
            r"\s+(?:GREAT DEAL|GOOD DEAL|DEAL)\b.*$",
            "",
            name,
            flags=re.I,
        )
        name = re.sub(
            r"\s+\d+%\s+less than usual.*$",
            "",
            name,
            flags=re.I,
        )
        name = re.sub(
            r"\s+(?:from|starting at)\s+(?:US\$|\$)\s?\d[\d,]*.*$",
            "",
            name,
            flags=re.I,
        )

        return cls._clean_text(name).strip(" ,-")

    @classmethod
    def _is_valid_hotel_name(cls, name: str) -> bool:
        if not name or len(name) < 3 or len(name) > 120:
            return False
        if name.casefold() in cls._NON_HOTEL_LABELS:
            return False
        if cls._INVALID_NAMES.match(name):
            return False
        if cls._extract_price(name):
            return False
        if cls._extract_rating(name):
            return False
        if cls._extract_reviews(name):
            return False
        return True

    @classmethod
    def _merge_hotel(
        cls,
        hotels_by_name: dict[str, HotelResult],
        hotel: HotelResult,
    ) -> None:
        key = re.sub(r"[^a-z0-9]+", "", hotel["name"].casefold())
        if not key:
            return

        existing = hotels_by_name.get(key)
        if existing is None:
            hotels_by_name[key] = hotel
            return

        if existing["price"] == "See live price" and hotel["price"] != "See live price":
            existing["price"] = hotel["price"]
        if existing["rating"] is None and hotel["rating"] is not None:
            existing["rating"] = hotel["rating"]
        if existing["reviews"] is None and hotel["reviews"] is not None:
            existing["reviews"] = hotel["reviews"]

        if (
            existing["description"].startswith("Open Google Travel")
            and not hotel["description"].startswith("Open Google Travel")
        ):
            existing["description"] = hotel["description"]

        existing["amenities"] = list(
            dict.fromkeys(existing["amenities"] + hotel["amenities"])
        )

        existing["location_highlight"] = (
            existing["location_highlight"]
            or hotel["location_highlight"]
        )
        existing["property_highlights"] = list(
            dict.fromkeys(
                existing["property_highlights"]
                + hotel["property_highlights"]
            )
        )
        existing["guest_mentions"] = list(
            dict.fromkeys(
                existing["guest_mentions"]
                + hotel["guest_mentions"]
            )
        )

        existing["image"] = existing["image"] or hotel["image"]

        if "qs=" in hotel["link"] and "qs=" not in existing["link"]:
            existing["link"] = hotel["link"]
        elif not existing["link"]:
            existing["link"] = hotel["link"]

    @classmethod
    def _extract_location_highlight(cls, text: str) -> str | None:
        """Extract a concise location-related highlight."""
        cleaned = cls._clean_accessibility_text(text)

        patterns = (
            r"\bExcellent location\b",
            r"\bGreat location\b",
            r"\bGood location\b",
            r"\bCentral location\b",
            r"\bConvenient location\b",
            r"\bExcellent neighborhood\b",
            r"\bGreat neighborhood\b",
        )

        for pattern in patterns:
            match = re.search(pattern, cleaned, re.I)
            if match:
                return match.group(0)[0].upper() + match.group(0)[1:]

        return None

    @classmethod
    def _extract_guest_mentions(cls, text: str) -> list[str]:
        """Extract and clean guest-review topics from Google Travel."""
        cleaned = cls._clean_accessibility_text(text)

        marker = re.search(
            r"People often mention\s*\|?\s*(.+)$",
            cleaned,
            re.I,
        )
        if marker is None:
            return []

        tail = marker.group(1)
        tail = re.split(
            r"\s*\|\s*(?:Excellent location|Great location|Good location|"
            r"Smoke-free property|Full-service laundry|View prices?|"
            r"Photos?|Book|Check availability)\b",
            tail,
            maxsplit=1,
            flags=re.I,
        )[0]

        # Google sometimes concatenates adjacent labels, for example:
        # "CleanlinessSleep" or "BarAir Conditioning".
        known_topics = (
            "Accessibility",
            "Air conditioning",
            "Atmosphere",
            "Bathroom",
            "Breakfast",
            "Cleanliness",
            "Comfort",
            "Dining",
            "Food",
            "Location",
            "Parking",
            "Property",
            "Room",
            "Service",
            "Sleep",
            "Staff",
            "Value",
            "Wellness",
            "Wi-Fi",
        )

        for topic in sorted(known_topics, key=len, reverse=True):
            tail = re.sub(
                rf"(?i)(?<=[a-z])(?={re.escape(topic)})",
                " · ",
                tail,
            )

        values = re.split(r"\s*[·•|,]\s*", tail)
        mentions: list[str] = []

        ignored_topics = {
            "property",
            "hotel",
            "rating",
            "reviews",
        }

        for value in values:
            item = cls._clean_text(value).strip(" .:-")
            if not item:
                continue

            # Remove duplicated rating summaries such as "3.6 (757)".
            if re.fullmatch(
                r"[1-5](?:\.\d+)?\s*\([\d,.]+\s*[KM]?\)",
                item,
                re.I,
            ):
                continue

            if re.search(
                r"reviews?|stars?|out of 5|price|deal|night|tax|fee|"
                r"people often mention|54321",
                item,
                re.I,
            ):
                continue

            if item.casefold() in ignored_topics:
                continue

            if len(item) > 32:
                continue

            mentions.append(item.title())

        return list(dict.fromkeys(mentions))[:4]

    @classmethod
    def _extract_property_highlights(
        cls,
        text: str,
        *,
        amenities: list[str],
        location_highlight: str | None,
        guest_mentions: list[str],
    ) -> list[str]:
        """Build a concise, deduplicated list of property features."""
        cleaned = cls._clean_accessibility_text(text)
        highlights: list[str] = list(amenities)

        known_highlights = (
            "Smoke-free property",
            "Full-service laundry",
            "Free Wi-Fi",
            "Free breakfast",
            "Free parking",
            "Pet-friendly",
            "Air conditioning",
            "Fitness center",
            "Business center",
            "Airport shuttle",
            "Room service",
            "Beach access",
            "Wheelchair accessible",
        )

        for highlight in known_highlights:
            if highlight.casefold() in cleaned.casefold():
                highlights.append(highlight)

        aliases = {
            "smoke-free": "Smoke-free property",
            "accessible": "Wheelchair accessible",
        }

        normalized: list[str] = []
        for item in highlights:
            clean_item = cls._clean_text(item)
            clean_item = aliases.get(clean_item.casefold(), clean_item)

            if not clean_item:
                continue
            if clean_item.casefold() in {"property", "hotel"}:
                continue
            normalized.append(clean_item)

        # Prefer the more descriptive form when both versions are present.
        normalized_keys = {item.casefold() for item in normalized}
        if "smoke-free property" in normalized_keys:
            normalized = [
                item for item in normalized
                if item.casefold() != "smoke-free"
            ]

        excluded = {
            location_highlight.casefold() if location_highlight else "",
            *(mention.casefold() for mention in guest_mentions),
        }

        return [
            item
            for item in dict.fromkeys(normalized)
            if item.casefold() not in excluded
        ][:6]

    @staticmethod
    def _clean_accessibility_text(text: str) -> str:
        """
        Remove Google rating-control artifacts such as '54321' while
        preserving useful labels and separators.
        """
        cleaned = str(text or "")
        cleaned = re.sub(r"(?<=\))\s*5\s*4\s*3\s*2\s*1", " ", cleaned)
        cleaned = re.sub(r"54321", " ", cleaned)
        cleaned = re.sub(
            r"(?i)People\s*often\s*mention\s*",
            " | People often mention | ",
            cleaned,
        )
        cleaned = re.sub(
            r"(?i)(Excellent location|Great location|Good location|"
            r"Smoke-free property|Full-service laundry)",
            r" | \1 | ",
            cleaned,
        )
        cleaned = re.sub(r"\s*·\s*", " · ", cleaned)
        cleaned = re.sub(r"\s*\|\s*", " | ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(" |")

    @classmethod
    def _normalize_amenities(
        cls,
        value: Any,
        raw_text: str,
    ) -> list[str]:
        amenities: list[str] = []
        if isinstance(value, list):
            amenities.extend(
                cleaned
                for item in value
                if (cleaned := cls._clean_text(item))
            )
        amenities.extend(cls._extract_amenities(raw_text))
        return list(dict.fromkeys(amenities))

    @classmethod
    def _extract_amenities(cls, text: str) -> list[str]:
        normalized = text.casefold()
        return [
            amenity
            for amenity in cls._AMENITIES
            if amenity.casefold() in normalized
        ]

    @staticmethod
    def _normalize_price(value: Any) -> str | None:
        text = TravelParser._clean_text(value)
        if not text:
            return None
        match = re.search(
            r"(?:US\$|\$)\s?\d[\d,]*(?:\.\d{1,2})?",
            text,
            re.I,
        )
        if match is None:
            return None
        return re.sub(r"^US\$\s?", "$", match.group(0), flags=re.I)

    @staticmethod
    def _extract_price(text: str) -> str | None:
        return TravelParser._normalize_price(text)

    @staticmethod
    def _coerce_rating(value: Any) -> float | None:
        if value is None:
            return None
        try:
            rating = float(value)
        except (TypeError, ValueError):
            return None
        return rating if 0 <= rating <= 5 else None

    @staticmethod
    def _extract_rating(text: str) -> float | None:
        """Extract a hotel rating from common Google Travel formats."""

        patterns = (
            # 4.3 out of 5 stars
            r"([1-5](?:\.\d+)?)\s+out of\s+5(?:\s+stars?)?",

            # 4.3 / 5
            r"([1-5](?:\.\d+)?)\s*/\s*5",

            # Rated 4.3
            r"\brated\s+([1-5](?:\.\d+)?)\b",

            # 4.3 stars
            r"\b([1-5](?:\.\d+)?)\s+stars?\b",

            # 4.3 (978 reviews)
            r"\b([1-5](?:\.\d+)?)\s*\(\s*[\d,.]+\s*reviews?\s*\)",

            # 4.3 · 978 reviews
            r"\b([1-5](?:\.\d+)?)\s*[·•|]\s*[\d,.]+\s+reviews?\b",

            # 4.3 followed somewhere nearby by review text
            r"\b([1-5](?:\.\d+)?)\b(?=.{0,25}\breviews?\b)",
        )

        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            if match:
                return TravelParser._coerce_rating(
                    match.group(1)
                )

        return None

    @staticmethod
    def _coerce_reviews(value: Any) -> int | None:
        if value is None:
            return None

        text = str(value).strip().casefold()
        multiplier = 1
        if text.endswith("k"):
            multiplier = 1_000
            text = text[:-1]
        elif text.endswith("m"):
            multiplier = 1_000_000
            text = text[:-1]

        try:
            if multiplier > 1:
                return int(float(text.replace(",", "")) * multiplier)
        except ValueError:
            return None

        digits = re.sub(r"[^\d]", "", text)
        return int(digits) if digits else None

    @staticmethod
    def _extract_reviews(text: str) -> int | None:
        match = re.search(
            r"(?:from\s+)?([\d,.]+\s*[KM]?)\s+"
            r"(?:Google\s+)?reviews?",
            text,
            re.I,
        )
        if match:
            return TravelParser._coerce_reviews(match.group(1))
        return None

    @classmethod
    def _build_description(
        cls,
        raw_text: str,
        name: str,
        amenities: list[str],
    ) -> str:
        if not raw_text:
            return ""

        cleaned_raw_text = cls._clean_accessibility_text(raw_text)

        excluded = {name.casefold(), *(item.casefold() for item in amenities)}
        candidates: list[str] = []

        for line in re.split(r"[\n|]", cleaned_raw_text):
            cleaned = cls._clean_text(line)
            if not cleaned or cleaned.casefold() in excluded:
                continue
            if cls._extract_price(cleaned):
                continue
            if re.search(
                r"reviews?|out of 5|stars?|book|view deal|"
                r"great deal|less than usual|photos? for|people often mention|54321",
                cleaned,
                re.I,
            ):
                continue
            if 12 <= len(cleaned) <= 240:
                candidates.append(cleaned)

        return candidates[0] if candidates else ""

    @classmethod
    def _build_hotel_link(cls, hotel_name: str, destination: str = "") -> str:
        search_query = hotel_name.strip()
        if destination.strip():
            search_query = f"{search_query} {destination.strip()}"
        return f"{cls.GOOGLE_TRAVEL_URL}?q={quote_plus(search_query)}"

    @classmethod
    def _normalize_url(cls, raw_url: str) -> str:
        if not raw_url or raw_url == "#":
            return ""
        return urljoin(cls.GOOGLE_BASE_URL, raw_url)

    @staticmethod
    def _clean_text(value: Any) -> str:
        if value is None:
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    @staticmethod
    def _unescape_snapshot_text(value: str) -> str:
        return (
            value.replace(r'\"', '"')
            .replace(r"\n", " ")
            .replace(r"\\", "\\")
            .strip()
        )