# F1 Analytics

A modern web application built to aggregate historical and live Formula 1 session telemetry, interval timing gaps, environmental track metrics, and team radio communications via the open-source **OpenF1 API**.

## 🏎️ Features
* **Fuzzy-Matched Session Routing:** Smart substring filtering automatically maps user selections to official FIA session naming conventions (e.g., matching "Qualifying Session" when "Qualifying" is selected).
* **Full-Bleed Leaderboard:** Clean, full-width table displaying P1–P20 standings, driver acronyms, constructor color badges, and calculated gap intervals relative to the race leader.
* **Interactive Team Radio:** Directly embeds HTML5 audio players to stream actual engineer-to-driver `.mp3` communications on demand.
* **Track Environment Metrics:** Real-time air/track temperatures, rainfall indicators, and wind telemetry snapshots.
* **Dynamic Year Range:** JavaScript auto-generation script handles available data seasons from 2023 onwards.

## 🛠️ Tech Stack
* **Backend:** Python (Flask) & `requests`
* **Frontend:** HTML5, CSS3 (Flexbox/Grid), and Asynchronous JavaScript (`fetch`)
