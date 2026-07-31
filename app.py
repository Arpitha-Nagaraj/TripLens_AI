from __future__ import annotations

import json
from typing import Any

import streamlit as st

from travelgpt.natural_language_agent import NaturalLanguageTravelAgent


st.set_page_config(
    page_title="TravelGPT",
    page_icon="✈️",
    layout="wide",
)


def initialize_session_state() -> None:
    """Initialize values that should persist across Streamlit reruns."""

    if "search_response" not in st.session_state:
        st.session_state.search_response = None

    if "search_error" not in st.session_state:
        st.session_state.search_error = None


@st.cache_resource
def get_travel_agent() -> NaturalLanguageTravelAgent:
    """
    Create the travel agent once and reuse it across Streamlit reruns.

    This avoids recreating the Gemini client and other application
    dependencies whenever Streamlit reruns the app.
    """
    return NaturalLanguageTravelAgent()


def format_rating(rating: float | None) -> str:
    """Format a hotel rating for display."""

    if rating is None:
        return "Rating unavailable"

    return f"⭐ {rating:.1f}"


def format_reviews(reviews: int | None) -> str:
    """Format a hotel review count for display."""

    if reviews is None:
        return "Review count unavailable"

    return f"{reviews:,} reviews"


def display_interpreted_request(
    interpreted_request: dict[str, Any],
) -> None:
    """Show how Gemini interpreted the user's request."""

    with st.expander("How TravelGPT understood your request"):
        destination_column, category_column, price_column = st.columns(3)

        with destination_column:
            st.markdown("**Destination**")
            st.write(
                interpreted_request.get(
                    "destination",
                    "Not specified",
                )
            )

        with category_column:
            st.markdown("**Category**")

            category = interpreted_request.get(
                "category",
                "Not specified",
            )

            st.write(str(category).title())

        with price_column:
            st.markdown("**Price preference**")

            price_preference = interpreted_request.get(
                "price_preference",
                "unspecified",
            )

            st.write(str(price_preference).title())

        st.markdown("**Search query sent to the browser**")

        st.code(
            str(
                interpreted_request.get(
                    "query",
                    "",
                )
            )
        )


def display_hotel_card(
    hotel: dict[str, Any],
    index: int,
) -> None:
    """Display one compact, polished hotel result."""

    with st.container(border=True):
        st.subheader(
            f"{index}. {hotel.get('name', 'Unknown hotel')}"
        )

        price = hotel.get("price") or "See live price"
        rating = hotel.get("rating")
        reviews = hotel.get("reviews")

        rating_text = (
            f"⭐ {rating:.1f}"
            if rating is not None
            else "⭐ Rating unavailable"
        )
        review_text = (
            f"📝 {reviews:,} reviews"
            if reviews is not None
            else "📝 Reviews unavailable"
        )
        price_text = (
            f"💲 {price}/night"
            if price != "See live price"
            else " See live price"
        )

        st.markdown(
            f"**{rating_text}** &nbsp;&nbsp; • &nbsp;&nbsp; "
            f"**{review_text}** &nbsp;&nbsp; • &nbsp;&nbsp; "
            f"**{price_text}**",
            unsafe_allow_html=True,
        )

        location_highlight = hotel.get("location_highlight")
        if location_highlight:
            st.markdown(f"📍 {location_highlight}")

        property_highlights = hotel.get("property_highlights") or []
        visible_property_highlights = property_highlights[:4]

        if visible_property_highlights:
            st.markdown("**🏠 Property**")
            property_text = " &nbsp; • &nbsp; ".join(
                visible_property_highlights
            )
            st.markdown(
                property_text,
                unsafe_allow_html=True,
            )

            remaining_count = (
                len(property_highlights)
                - len(visible_property_highlights)
            )
            if remaining_count > 0:
                st.caption(
                    f"+{remaining_count} more propert"
                    f"{'y feature' if remaining_count == 1 else 'y features'}"
                )

        guest_mentions = hotel.get("guest_mentions") or []

        if guest_mentions:
            st.markdown("**💬 Guests mention**")
            st.markdown(
                " &nbsp; • &nbsp; ".join(guest_mentions),
                unsafe_allow_html=True,
            )

        link = hotel.get("link")

        if link:
            st.link_button(
                "View on Google Travel",
                link,
                use_container_width=True,
            )


def display_results(
    response: dict[str, Any],
) -> None:
    """Render the complete response returned by the travel agent."""

    interpreted_request = response.get(
        "interpreted_request",
        {},
    )

    search_response = response.get(
        "search_response",
        {},
    )

    display_interpreted_request(
        interpreted_request
    )

    results = search_response.get(
        "results",
        [],
    )

    result_count = search_response.get(
        "count",
        len(results),
    )

    requested_limit = interpreted_request.get(
        "limit",
        result_count,
    )

    st.divider()
    st.subheader("Hotel results")

    if not results:
        st.warning(
            "No usable hotel results were found. "
            "Try changing the destination or search wording."
        )
        return

    st.success(
        f"Found {result_count} hotel"
        f"{'' if result_count == 1 else 's'}."
    )

    st.info(
        "Hotel prices are snapshots from Google search results. "
        "The final price may differ based on dates, room type, "
        "availability, provider, taxes, and fees."
    )

    if (
        isinstance(requested_limit, int)
        and result_count < requested_limit
    ):
        st.info(
            f"You requested up to {requested_limit} results, "
            f"and TravelGPT found {result_count} usable hotel "
            "results during this search."
        )

    for index, hotel in enumerate(
        results,
        start=1,
    ):
        display_hotel_card(
            hotel=hotel,
            index=index,
        )

    st.divider()

    st.download_button(
        label="Download results as JSON",
        data=json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
        ),
        file_name="travelgpt_results.json",
        mime="application/json",
        use_container_width=True,
    )


def run_search(
    user_request: str,
) -> None:
    """Execute the complete natural-language hotel search."""

    st.session_state.search_error = None
    st.session_state.search_response = None

    try:
        agent = get_travel_agent()

        with st.spinner(
            "TravelGPT is understanding your request "
            "and searching for hotels..."
        ):
            response = agent.search(
                user_request
            )

        st.session_state.search_response = response

    except ValueError as error:
        st.session_state.search_error = str(error)

    except Exception as error:
        st.session_state.search_error = (
            "TravelGPT could not complete the search. "
            f"Details: {error}"
        )


def main() -> None:
    """Render the TravelGPT Streamlit application."""

    initialize_session_state()

    st.title("TravelGPT ✈️")

    st.write(
        "Describe the hotel you are looking for in natural language. "
        "TravelGPT uses Gemini to understand your request and "
        "Playwright MCP to search current browser results."
    )

    st.caption(
        "Example: Find me five affordable hotels in San Francisco"
    )

    with st.form(
        "travel_search_form",
        clear_on_submit=False,
    ):
        user_request = st.text_area(
            "What would you like to find?",
            value=(
                "Find me five affordable hotels "
                "in San Francisco"
            ),
            height=120,
            placeholder=(
                "Example: Find me three luxury hotels "
                "in New York"
            ),
        )

        submitted = st.form_submit_button(
            "Search hotels",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        normalized_request = user_request.strip()

        if not normalized_request:
            st.session_state.search_error = (
                "Please enter a travel request."
            )
            st.session_state.search_response = None
        else:
            run_search(
                normalized_request
            )

    if st.session_state.search_error:
        st.error(
            st.session_state.search_error
        )

    if st.session_state.search_response:
        display_results(
            st.session_state.search_response
        )


if __name__ == "__main__":
    main()