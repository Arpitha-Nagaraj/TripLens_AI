# ✈️ TripLens AI

TripLens is an AI-powered travel assistant that uses **Large Language Models (Gemini)** together with **Model Context Protocol (MCP)** servers to retrieve and organize live travel information.

Instead of relying on traditional travel APIs, TripLens AI uses **Playwright MCP** to control a real browser, search Google Travel, extract hotel information, and present it in a clean, interactive Streamlit application.

---

## 🚀 Features

### 🤖 Natural Language Search

Users can search using plain English.

Example:

```
Find me 5 affordable hotels in San Francisco
```

The Gemini model understands the request and extracts:

- Destination
- Search category
- Budget preference
- Number of results

---

### 🌐 Browser Automation using Playwright MCP

TripLens uses **Playwright MCP** instead of scraping HTML.

The browser agent automatically:

- Opens Google Travel
- Performs hotel searches
- Waits for page loading
- Scrolls through hotel listings
- Captures accessibility snapshots
- Returns structured browser data

---

### 🏨 Rich Hotel Information

The application extracts and displays:

- Hotel name
- Nightly price
- Hotel rating
- Review count
- Location highlights
- Property highlights
- Guest review topics
- Google Travel link

Example:

```
San Remo Hotel

⭐ 4.3
📝 978 reviews
💲 $71/night

📍 Excellent location

🏠 Property
• Free Wi-Fi
• Free breakfast
• Pool
• Hot tub

💬 Guests mention
• Location
• Wellness
• Service
```

---

### 🎨 Clean Streamlit Interface

Each hotel is displayed in a modern card including:

- Hotel information
- Price
- Ratings
- Property highlights
- Guest review highlights
- Direct Google Travel link

---

## 🏗️ Project Architecture

```

User
│
▼
Natural Language Query

│
▼

Gemini LLM

(Extract Intent)

│
▼

Browser MCP Client

│
▼

Playwright MCP Server

│
▼

Google Travel

│
▼

Accessibility Snapshot

│
▼

Travel Parser

│
▼

Structured Hotel Data

│
▼

Streamlit UI

```

---

## 📂 Project Structure

```

TravelGPT/
│
├── app.py
├── requirements.txt
│
├── travelgpt/
│   ├── browser_client.py
│   ├── natural_language_agent.py
│   ├── travel_parser.py
│   └── models.py
│
└── README.md

```

---

## ⚙️ Technologies Used

### AI

- Google Gemini
- Prompt Engineering

### MCP

- Playwright MCP

### Backend

- Python

### UI

- Streamlit

### Browser Automation

- Playwright MCP Server

---

## 🔄 Current Workflow

1. User enters a natural language travel request.
2. Gemini extracts structured search parameters.
3. Browser MCP launches Google Travel.
4. Playwright performs browser interactions.
5. Accessibility snapshots are captured.
6. Travel parser extracts structured hotel information.
7. Streamlit renders polished hotel cards.

---

## 📸 Example Search

Input

```
Find me affordable hotels in New York
```

Output

```
✔ 5 hotels

⭐ Ratings
📝 Reviews
💲 Prices
📍 Location highlights
🏠 Property highlights
💬 Guest review topics
🔗 Google Travel links
```

---

# Roadmap

## ✅ Phase 1 — Natural Language Search

- [x] Gemini request understanding
- [x] Browser MCP integration
- [x] Google Travel automation

---

## ✅ Phase 2 — Hotel Extraction

- [x] Hotel names
- [x] Prices
- [x] Ratings
- [x] Review counts
- [x] Property highlights
- [x] Guest review topics
- [x] Clean UI

---

## 🚧 Phase 3 — Hotel Images

Planned:

- Display hotel images
- Rich hotel cards
- Better descriptions

---

## 🚧 Phase 4 — Google Maps MCP

Planned:

- Distance calculations
- Travel time
- Nearby attractions
- Route planning

Example:

```
Find hotels within 15 minutes of Times Square
```

---

## 🚧 Phase 5 — Weather MCP

Planned:

- Current weather
- 7-day forecast
- Best travel dates

Example:

```
Find hotels in Seattle this weekend with sunny weather
```

---

## 🚧 Phase 6 — AI Travel Planner

TripLensAI becomes a complete travel assistant.

Example:

```
Plan me a 3-day trip to San Francisco
Budget: $800
Need a hotel near Salesforce Tower
Include restaurants and sightseeing
```

TripLensAI will coordinate:

- Browser MCP
- Google Maps MCP
- Weather MCP
- Gemini reasoning

to generate a complete travel itinerary.

---

## 🎯 Future Enhancements

- Hotel image gallery
- Restaurant recommendations
- Flight search
- Personalized travel itineraries
- Cost estimation
- Interactive maps
- Save favorite hotels
- Trip export (PDF)
- Multi-city trip planning
- Voice-based travel assistant

---

## 💡 Why MCP?

Instead of relying on paid travel APIs, TripLensAI demonstrates how **Model Context Protocol (MCP)** enables LLMs to interact with real applications through browser automation.

This allows the assistant to retrieve live travel information directly from Google Travel while keeping the architecture flexible and extensible for additional MCP tools.

---

## 👨‍💻 Author

**Arpitha Nagaraj**

M.S. Computer Engineering
San José State University

Interested in:

- AI Agents
- MCP
- Distributed Systems
- Backend Engineering
- Full Stack Development
