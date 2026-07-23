import requests
import webbrowser
from threading import Timer
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

BASE_URL = "https://api.openf1.org/v1"

# Official FIA F1 Point Distributions
STANDARD_POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
SPRINT_POINTS   = {1: 8,  2: 7,  3: 6,  4: 5,  5: 4,  6: 3, 7: 2, 8: 1}

@app.route('/')
def home():
    return render_template_string(HTML_LAYOUT)

@app.route('/get_race_data', methods=['POST'])
def get_race_data():
    user_data = request.json
    year = user_data.get('year')
    country = user_data.get('country')
    session_search = user_data.get('session')

    # 1. Look up the Session Key
    lookup_url = f"{BASE_URL}/sessions?year={year}&country_name={country}"
    try:
        all_sessions = requests.get(lookup_url).json()
    except Exception:
        return jsonify({"error": "Failed to connect to the OpenF1 database."}), 500

    if not all_sessions or not isinstance(all_sessions, list):
        return jsonify({"error": f"No Grand Prix data found for {year} {country}."}), 404

    matched_session = None
    for s in all_sessions:
        current_name = s.get('session_name', '').lower()
        search_term = session_search.lower()
        if search_term == current_name or search_term in current_name:
            matched_session = s
            break

    if not matched_session:
        return jsonify({"error": f"Could not find matching session '{session_search}'."}), 404

    session_key = matched_session['session_key']
    location = matched_session['location']
    actual_session_name = matched_session['session_name']

    # 2. Get Weather Data Safely
    weather_summary = "Weather details are currently offline for this historical event."
    try:
        weather_res = requests.get(f"{BASE_URL}/weather?session_key={session_key}").json()
        if weather_res and isinstance(weather_res, list):
            latest_weather = weather_res[-1]
            is_raining = " Yes" if latest_weather.get('rainfall') == 1 else " No"
            weather_summary = f" Air Temp: {latest_weather.get('air_temperature')}°C  |  Track Temp: {latest_weather.get('track_temperature')}°C  |  Rainfall: {is_raining}  |  Wind Speed: {latest_weather.get('wind_speed')} m/s"
    except Exception:
        pass

    # 3. Get Team Radio Clips Safely
    radio_lookup = {}
    try:
        radio_res = requests.get(f"{BASE_URL}/team_radio?session_key={session_key}").json()
        if radio_res and isinstance(radio_res, list):
            for audio in radio_res:
                driver_num = audio.get('driver_number')
                url = audio.get('recording_url')
                if url:
                    radio_lookup[driver_num] = url
    except Exception:
        pass

    # 4. Get Driver Details mapping
    driver_lookup = {}
    try:
        drivers_res = requests.get(f"{BASE_URL}/drivers?session_key={session_key}").json()
        if isinstance(drivers_res, list):
            driver_lookup = {d.get('driver_number'): {
                'acronym': d.get('name_acronym', 'UNK'),
                'team': d.get('team_name', 'Unknown Team'),
                'color': d.get('team_colour', 'FFFFFF')
            } for d in drivers_res}
    except Exception:
        pass

    # 5. Get Standings & Lap Totals
    results_res = []
    laps_lookup = {}

    try:
        results_res = requests.get(f"{BASE_URL}/session_result?session_key={session_key}").json()
        if not isinstance(results_res, list):
            results_res = []

        # Fetch total laps per driver from the /laps endpoint
        laps_res = requests.get(f"{BASE_URL}/laps?session_key={session_key}").json()
        if isinstance(laps_res, list):
            for l in laps_res:
                d_num = l.get('driver_number')
                l_num = l.get('lap_number')
                if d_num and l_num:
                    laps_lookup[d_num] = max(laps_lookup.get(d_num, 0), l_num)
    except Exception:
        pass

    # Identify session point rules
    is_sprint = "sprint" in actual_session_name.lower() and "shootout" not in actual_session_name.lower()
    is_race = "race" in actual_session_name.lower() and not is_sprint

    output_rows = []
    if not results_res and driver_lookup:
        for num, profile in driver_lookup.items():
            output_rows.append({
                "position": "N/A",
                "acronym": profile['acronym'],
                "team": profile['team'],
                "color": f"#{profile['color']}",
                "laps": "-",
                "interval": "-",
                "points": "0",
                "radio_url": radio_lookup.get(num, None)
            })
    else:
        sorted_standings = sorted(
            results_res,
            key=lambda x: x.get('position') if (x.get('position') is not None and str(x.get('position')).isdigit()) else 99
        )

        for i, row in enumerate(sorted_standings):
            driver_num = row.get('driver_number')
            p_val = row.get('position')

            # Pull completed laps from laps_lookup dictionary
            laps_val = laps_lookup.get(driver_num, "-")
            profile = driver_lookup.get(driver_num, {'acronym': 'UNK', 'team': 'Unknown Team', 'color': 'FFFFFF'})

            if i == 0:
                interval_str = "Leader"
            else:
                gap_val = row.get('time_diff_to_next') or row.get('gap_to_leader')
                if gap_val is not None:
                    interval_str = f"+{gap_val}s" if isinstance(gap_val, (int, float)) else str(gap_val)
                else:
                    interval_str = "+0.000s"

            # Points Processor
            earned_points = 0
            if p_val is not None and str(p_val).isdigit():
                pos_int = int(p_val)
                if is_race:
                    earned_points = STANDARD_POINTS.get(pos_int, 0)
                elif is_sprint:
                    earned_points = SPRINT_POINTS.get(pos_int, 0)

            output_rows.append({
                "position": f"P{p_val}" if p_val is not None else "N/A",
                "acronym": profile['acronym'],
                "team": profile['team'],
                "color": f"#{profile['color']}",
                "laps": laps_val,
                "interval": interval_str,
                "points": str(earned_points) if earned_points > 0 else "-",
                "radio_url": radio_lookup.get(driver_num, None)
            })

    return jsonify({
        "location": location,
        "session_name": actual_session_name,
        "year": year,
        "weather": weather_summary,
        "results": output_rows
    })

@app.route('/get_telemetry', methods=['POST'])
def get_telemetry():
    req = request.json
    session_key = req.get('session_key')
    driver_numbers = req.get('driver_numbers', [])

    if not session_key or not driver_numbers:
        return jsonify({"error": "Missing session_key or selected drivers"}), 400

    telemetry_data = {}

    # Limit to max 3 drivers at a time so API response is fast
    for d_num in driver_numbers[:3]:
        try:
            # Query car_data for this driver
            url = f"{BASE_URL}/car_data?session_key={session_key}&driver_number={d_num}"
            car_res = requests.get(url).json()

            if isinstance(car_res, list) and len(car_res) > 0:
                # Downsample data (take every 5th point) to keep the browser running smooth
                sampled = car_res[::5]
                speeds = [item.get('speed', 0) for item in sampled]

                telemetry_data[d_num] = {
                    "speeds": speeds,
                    "sample_count": len(speeds)
                }
        except Exception:
            continue

    return jsonify({"telemetry": telemetry_data})

SEASON_2026_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <title>F1 Analytics - 2026 Podiums</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #111214; color: white; margin: 0; display: flex; min-height: 100vh; overflow-x: hidden; }

        /* CLEAN FIXED ICON-ONLY SIDEBAR (65px) */
        aside {
            width: 65px;
            background: #1a1b1e;
            border-right: 1px solid #2e3137;
            display: flex;
            flex-direction: column;
            align-items: center;
            position: fixed;
            top: 0;
            bottom: 0;
            left: 0;
            z-index: 1000;
            padding: 20px 0;
        }

        .sidebar-logo {
            font-size: 22px;
            margin-bottom: 30px;
            cursor: pointer;
        }

        .nav-menu { display: flex; flex-direction: column; gap: 15px; list-style: none; padding: 0; margin: 0; width: 100%; align-items: center; }
        .nav-item { width: 100%; display: flex; justify-content: center; }

        .nav-item a {
            display: flex;
            align-items: center;
            justify-content: center;
            color: #8a8f9d;
            text-decoration: none;
            font-size: 18px;
            width: 42px;
            height: 42px;
            border-radius: 8px;
            transition: all 0.2s ease;
            position: relative;
        }

        .nav-item a:hover { color: #fff; background: #252830; }
        .nav-item a.active { color: #fff; background: #e10600; }

        /* HOVER TOOLTIPS FOR ICONS */
        .nav-item a::after {
            content: attr(data-tooltip);
            position: absolute;
            left: 55px;
            background: #2f333d;
            color: #fff;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            border: 1px solid #3e4350;
        }
        .nav-item a:hover::after { opacity: 1; }

        /* MAIN CONTENT AREA & TOP HEADER BAR */
        .main-wrapper { margin-left: 65px; flex-grow: 1; display: flex; flex-direction: column; min-width: 0; }
        header { background: #1f2125; padding: 20px 40px; border-bottom: 1px solid #2e3137; position: sticky; top: 0; z-index: 900; }
        .header-title { font-size: 18px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: #fff; margin: 0; }
        .header-title span { color: #e10600; }

        .container { max-width: 1400px; margin: 30px auto; padding: 0 40px; width: 100%; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 25px; }

        .card { background: #1a1b1e; border: 1px solid #2e3137; border-radius: 8px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.2); display: flex; flex-direction: column; justify-content: space-between; }
        .card-header { font-size: 16px; font-weight: 800; margin-bottom: 10px; color: #fff; border-bottom: 1px solid #2e3137; padding-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        .card-date { font-size: 11px; color: #666; font-weight: normal; }

        .map-wrapper { width: 100%; height: 160px; background: #151619; border-radius: 6px; display: flex; align-items: center; justify-content: center; padding: 10px; margin-bottom: 15px; border: 1px solid #25272c; }
        .circuit-img { max-width: 100%; max-height: 100%; object-fit: contain; }

        /* PODIUM ROWS & SYMMETRICAL ACCENT BAR */
        .podium-row {
            display: flex;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #23252a;
        }
        .podium-row:last-child { border-bottom: none; }

        .badge {
            font-weight: 900;
            width: 40px;
            font-size: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .p1 { color: #ffd700; }
        .p2 { color: #c0c0c0; }
        .p3 { color: #cd7f32; }

        /* SYMMETRICAL ACCENT BAR CONTAINER */
        .driver-card-block {
            border-left: 4px solid;
            padding-left: 12px;
            margin-left: 5px;
            display: flex;
            flex-direction: column;
            justify-content: center;
            gap: 2px;
        }

        .driver-name {
            font-weight: 800;
            font-size: 15px;
            color: #fff;
            letter-spacing: 0.5px;
            line-height: 1.1;
        }

        .team-name {
            font-size: 12px;
            color: #888;
            font-weight: 500;
            line-height: 1.1;
        }
    </style>
</head>
<body>

    <aside>
        <div class="sidebar-trigger">
            <span class="menu-icon">☰</span>
            <span class="brand-text">F1 <span>Analytics</span></span>
        </div>
        <ul class="nav-menu">
            <li class="nav-item">
                <a href="/">
                    <span class="nav-icon">📊</span>
                    <span>Telemetry</span>
                </a>
            </li>
            <li class="nav-item">
                <a href="/season_2026" class="active">
                    <span class="nav-icon">🏆</span>
                    <span>2026 Podiums</span>
                </a>
            </li>
        </ul>
    </aside>

    <div class="main-wrapper">
        <header>
            <h1 class="header-title">F1 <span>Analytics</span> — 2026 Season Podiums</h1>
        </header>

        <div class="container">
            <div class="grid">
                {% for race in races %}
                <div class="card">
                    <div>
                        <div class="card-header">
                            <span>📍 {{ race.location }}</span>
                            <span class="card-date">{{ race.date }}</span>
                        </div>

                        <div class="map-wrapper">
                            {% if race.circuit_image %}
                            <img src="{{ race.circuit_image }}" alt="{{ race.location }} Track Map" class="circuit-img">
                            {% else %}
                            <span style="color:#555; font-size:12px;">🏎️ Track Map Offline</span>
                            {% endif %}
                        </div>
                    </div>

                    <div>
                        {% for p in race.podium %}
                        <div class="podium-row">
                            <span class="badge {% if loop.index == 1 %}p1{% elif loop.index == 2 %}p2{% else %}p3{% endif %}">
                                {% if loop.index == 1 %}🥇{% elif loop.index == 2 %}🥈{% else %}🥉{% endif %}
                            </span>
                            <div class="driver-card-block" style="border-color: {{ p.color }};">
                                <span class="driver-name">{{ p.driver }}</span>
                                <span class="team-name">{{ p.team }}</span>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                </div>
                {% else %}
                <p style="color:#666;">No completed 2026 Grand Prix podium records found yet.</p>
                {% endfor %}
            </div>
        </div>
    </div>

</body>
</html>
"""

HTML_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <title>F1 Analytics</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #111214; color: white; margin: 0; display: flex; min-height: 100vh; overflow-x: hidden; }

        /* CLEAN FIXED ICON-ONLY SIDEBAR (65px) */
        aside {
            width: 65px;
            background: #1a1b1e;
            border-right: 1px solid #2e3137;
            display: flex;
            flex-direction: column;
            align-items: center;
            position: fixed;
            top: 0;
            bottom: 0;
            left: 0;
            z-index: 1000;
            padding: 20px 0;
        }

        .sidebar-logo {
            font-size: 22px;
            margin-bottom: 30px;
            cursor: pointer;
        }

        .nav-menu { display: flex; flex-direction: column; gap: 15px; list-style: none; padding: 0; margin: 0; width: 100%; align-items: center; }
        .nav-item { width: 100%; display: flex; justify-content: center; }

        .nav-item a {
            display: flex;
            align-items: center;
            justify-content: center;
            color: #8a8f9d;
            text-decoration: none;
            font-size: 18px;
            width: 42px;
            height: 42px;
            border-radius: 8px;
            transition: all 0.2s ease;
            position: relative;
        }

        .nav-item a:hover { color: #fff; background: #252830; }
        .nav-item a.active { color: #fff; background: #e10600; }

        /* HOVER TOOLTIPS FOR SIDEBAR ICONS */
        .nav-item a::after {
            content: attr(data-tooltip);
            position: absolute;
            left: 55px;
            background: #2f333d;
            color: #fff;
            padding: 5px 10px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s ease;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
            border: 1px solid #3e4350;
            z-index: 1100;
        }
        .nav-item a:hover::after { opacity: 1; }

        /* MAIN WRAPPER & HEADER */
        .main-wrapper { margin-left: 65px; flex-grow: 1; display: flex; flex-direction: column; min-width: 0; }
        header { background: #1f2125; padding: 15px 40px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2e3137; position: sticky; top: 0; z-index: 900; }
        .header-brand { font-size: 18px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; color: #fff; margin: 0; }
        .header-brand span { color: #e10600; }

        .search-box { display: flex; gap: 10px; }
        select, button { padding: 10px 14px; border: none; border-radius: 4px; background: #2f333d; color: white; font-size: 14px; outline: none; }
        select { cursor: pointer; min-width: 140px; }
        button { background: #e10600; font-weight: bold; cursor: pointer; transition: 0.2s; padding: 10px 20px; }
        button:hover { background: #b80500; }

        /* DASHBOARD CARDS & TABLES */
        .page-content { width: 100%; max-width: 1400px; padding: 30px 40px; display: flex; flex-direction: column; gap: 30px; }
        .headline-card { background: #1a1b1e; border: 1px solid #2e3137; border-radius: 8px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); }
        .weather-banner { background: #18282c; padding: 15px 20px; border-radius: 6px; font-size: 14px; color: #00E1D9; border-left: 4px solid #00E1D9; font-weight: 500; margin-top: 15px; }
        .section-wrapper { background: #1a1b1e; border: 1px solid #2e3137; border-radius: 8px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); width: 100%; }
        .section-title { font-size: 14px; font-weight: 700; text-transform: uppercase; color: #888; margin-bottom: 20px; letter-spacing: 1px; border-bottom: 1px solid #2e3137; padding-bottom: 10px; }

        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 14px 20px; border-bottom: 1px solid #25272c; vertical-align: middle; }
        th { color: #555; text-transform: uppercase; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; background: #1a1b1e; }
        th:nth-child(1), td:nth-child(1) { width: 90px; font-size: 15px; }
        th:nth-child(2), td:nth-child(2) { width: 100px; }
        th:nth-child(3), td:nth-child(3) { width: 28%; }
        th:nth-child(4), td:nth-child(4) { width: 95px; text-align: center; }
        th:nth-child(5), td:nth-child(5) { width: 15%; }
        th:nth-child(6), td:nth-child(6) { width: 85px; text-align: center; }
        th:nth-child(7), td:nth-child(7) { width: 160px; }

        tr:hover { background: #22242a; }
        .team-container { display: flex; align-items: stretch; }
        .team-badge { border-left: 4px solid; padding-left: 12px; display: inline-flex; align-items: center; font-weight: 500; }
        audio { height: 26px; width: 145px; }

        .analytics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 40px; }
        .placeholder-card { background: #1a1b1e; border: 1px dashed #3e424c; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #5e6473; font-size: 14px; text-align: center; padding: 60px 20px; min-height: 400px; }
        .placeholder-card span { font-size: 32px; margin-bottom: 15px; }
    </style>
</head>

<body>

    <!-- HOVERABLE DRAWER SIDEBAR -->
    <aside>
        <div class="sidebar-logo">🏎️</div>
        <ul class="nav-menu">
            <li class="nav-item">
                <a href="/" class="active" data-tooltip="Telemetry Dashboard">
                    📊
                </a>
            </li>
            <li class="nav-item">
                <a href="/season_2026" data-tooltip="2026 Podiums">
                    🏆
                </a>
            </li>
        </ul>
    </aside>

    <!-- MAIN DASHBOARD CONTENT -->
    <div class="main-wrapper">
        <header>
            <h1 class="header-title">F1 <span>Analytics</span></h1>

            <div class="search-box">
                <select id="year">
                    <option value="2026">2026</option>
                    <option value="2025">2025</option>
                    <option value="2024">2024</option>
                    <option value="2023" selected>2023</option>
                </select>
                <select id="country">
                    <option value="Abu Dhabi">Abu Dhabi</option>
                    <option value="Australia">Australia</option>
                    <option value="Austria">Austria</option>
                    <option value="Azerbaijan">Azerbaijan</option>
                    <option value="Bahrain">Bahrain</option>
                    <option value="Belgium" selected>Belgium</option>
                    <option value="Brazil">Brazil</option>
                    <option value="Canada">Canada</option>
                    <option value="China">China</option>
                    <option value="Great Britain">Great Britain</option>
                    <option value="Hungary">Hungary</option>
                    <option value="Italy">Italy</option>
                    <option value="Japan">Japan</option>
                    <option value="Mexico">Mexico</option>
                    <option value="Monaco">Monaco</option>
                    <option value="Netherlands">Netherlands</option>
                    <option value="Qatar">Qatar</option>
                    <option value="Saudi Arabia">Saudi Arabia</option>
                    <option value="Singapore">Singapore</option>
                    <option value="Spain">Spain</option>
                    <option value="United States">United States</option>
                </select>
                <select id="session">
                    <option value="Race" selected>Race</option>
                    <option value="Qualifying">Qualifying</option>
                    <option value="Sprint">Sprint</option>
                    <option value="Practice 1">Practice 1</option>
                    <option value="Practice 2">Practice 2</option>
                    <option value="Practice 3">Practice 3</option>
                </select>
                <button onclick="searchRace()">Search</button>
            </div>
        </header>

    <!-- FULL PAGE SCROLLABLE MAIN LAYOUT SECTION -->
    <div class="page-content">

        <!-- Summary Headline Segment -->
        <div class="headline-card">
            <h2 id="summaryTitle" style="margin: 0 0 5px 0; font-size: 28px; color: #fff;">No Event Selected</h2>
            <p id="summarySubtitle" style="margin: 0; color: #888; font-size: 15px;">Use the selection navbar at the top to load telemetry data streams.</p>
            <div id="weatherContainer" class="weather-banner" style="display: none;"></div>
        </div>

        <FULL SCREEN WIDTH LEADERBOARD
        <div class="section-wrapper">
            <div class="section-title">Official Session Leaderboard</div>
            <table>
                <thead>
                    <tr>
                        <th>Position</th>
                        <th>Driver</th>
                        <th>Constructor Team</th>
                        <th style="text-align: center;">Laps</th>
                        <th>Interval Gap</th>
                        <th style="text-align: center;">Pts</th>
                        <th> Team Radio Feed</th>
                    </tr>
                </thead>
                <tbody id="resultsTableBody">
                    <tr><td colspan="7" style="text-align:center; color:#555; padding: 60px;">Select filters above and hit search to load data rows.</td></tr>
                </tbody>
            </table>
        </div>

        <!-- SECTION 2: DOWNWARD SCROLL ANALYTICS GRID CONTENT PLACEHOLDERS -->
        <div class="analytics-grid">
            <div class="section-wrapper">
    <div class="section-title" style="display:flex; justify-content:space-between; align-items:center;">
        <span>📈 Speed Telemetry Overlay</span>
        <span id="telemetryStatus" style="font-size:11px; color:#888; text-transform:none;">Select drivers after searching</span>
    </div>

    <!-- DRIVER SELECTION AREA -->
    <div id="driverPillsContainer" style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:15px;">
        <span style="color:#666; font-size:12px;">No driver telemetry available yet. Search a race first!</span>
    </div>

    <!-- CANVAS CHART -->
    <div style="position: relative; height: 320px; width: 100%;">
        <canvas id="telemetryChart"></canvas>
    </div>
</div>

            <div class="section-wrapper" style="padding:0; border:none; background:none;">
                <div class="section-title" style="margin-bottom:15px;">Live Track Map </div>
                <div class="placeholder-card">
                    <span>🗺️</span>
                    <b>Interactive Track Map </b>
                    <p style="margin: 5px 0 0 0; font-size:12px; max-width:280px; color:#666;">This zone is ready for rendering your continuous (X, Y) coordinate loop tracking dots matrix.</p>
                </div>
            </div>
        </div>

    </div>

    <script>
        let currentSessionKey = null;
        let driverColorMap = {};
        let selectedDrivers = new Set();
        let chartInstance = null;

        window.addEventListener('DOMContentLoaded', () => {});

        function searchRace() {
            const tableBody = document.getElementById('resultsTableBody');
            tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#888; padding: 60px;">⏳ Accessing OpenF1 telemetry data streams...</td></tr>`;

            const payload = {
                year: document.getElementById('year').value,
                country: document.getElementById('country').value,
                session: document.getElementById('session').value
            };

            fetch('/get_race_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if(data.error) {
                    alert(data.error);
                    tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#e10600; padding: 60px;">❌ Error: ${data.error}</td></tr>`;
                    return;
                }

                document.getElementById('summaryTitle').innerText = `${data.year} ${data.location} Grand Prix`;
                document.getElementById('summarySubtitle').innerText = `Official Session Format Record: ${data.session_name}`;

                const weatherBanner = document.getElementById('weatherContainer');
                weatherBanner.innerText = data.weather;
                weatherBanner.style.display = 'block';

                tableBody.innerHTML = "";
                driverColorMap = {};
                selectedDrivers.clear();

                const pillsContainer = document.getElementById('driverPillsContainer');
                pillsContainer.innerHTML = "";

                data.results.forEach(driver => {
                    // Extract driver number from row or profile map
                    const dNum = driver.driver_number || driver.acronym;
                    driverColorMap[driver.acronym] = { color: driver.color, num: dNum };

                    // Render Table Row
                    const radioCell = driver.radio_url
                        ? `<audio controls src="${driver.radio_url}"></audio>`
                        : `<span style="color:#444; font-size:11px;">No Audio</span>`;

                    const ptsDisplay = driver.points !== "-"
                        ? `<b style="color:#fff; font-size:14px;">${driver.points}</b>`
                        : `<span style="color:#444;">0</span>`;

                    const row = `<tr>
                        <td><b style="color:#fff;">${driver.position}</b></td>
                        <td><b style="color:#fff; background:#22252c; padding:4px 8px; border-radius:4px;">${driver.acronym}</b></td>
                        <td>
                            <div class="team-container">
                                <span class="team-badge" style="border-color: ${driver.color}; color:#aaa;">${driver.team}</span>
                            </div>
                        </td>
                        <td style="text-align: center; font-weight: 500; color: #fff;">${driver.laps}</td>
                        <td style="color:#00E1D9; font-weight:600; font-size:13px; letter-spacing:0.5px;">${driver.interval}</td>
                        <td style="text-align: center;">${ptsDisplay}</td>
                        <td>${radioCell}</td>
                    </tr>`;
                    tableBody.innerHTML += row;

                    // Render Interactive Driver Pill
                    const pill = document.createElement('button');
                    pill.style.cssText = `background:#22252c; color:#888; border:1px solid #333; padding:4px 10px; border-radius:15px; font-size:11px; font-weight:bold; cursor:pointer; transition:0.2s;`;
                    pill.innerText = driver.acronym;
                    pill.onclick = () => toggleDriverTelemetry(driver.acronym, dNum, pill, driver.color);
                    pillsContainer.appendChild(pill);
                });

                // Store current session key from backend response (Pass session_key in get_race_data return)
                currentSessionKey = data.session_key;
                initChart();
            })
            .catch(err => {
                tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#e10600; padding: 60px;">❌ Connection Failed</td></tr>`;
            });
        }

        function toggleDriverTelemetry(acronym, dNum, pillElement, teamColor) {
            if (!currentSessionKey) return;

            if (selectedDrivers.has(dNum)) {
                selectedDrivers.delete(dNum);
                pillElement.style.background = "#22252c";
                pillElement.style.color = "#888";
                pillElement.style.borderColor = "#333";
            } else {
                if (selectedDrivers.size >= 3) {
                    alert("You can compare up to 3 drivers simultaneously.");
                    return;
                }
                selectedDrivers.add(dNum);
                pillElement.style.background = teamColor;
                pillElement.style.color = "#fff";
                pillElement.style.borderColor = teamColor;
            }

            fetchTelemetryData();
        }

        function initChart() {
            const ctx = document.getElementById('telemetryChart').getContext('2d');
            if (chartInstance) chartInstance.destroy();

            chartInstance = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { display: false },
                        y: {
                            grid: { color: '#2a2d34' },
                            ticks: { color: '#888', font: { size: 10 } },
                            title: { display: true, text: 'Speed (km/h)', color: '#666', font: { size: 11 } }
                        }
                    },
                    plugins: {
                        legend: { labels: { color: '#fff', font: { weight: 'bold' } } }
                    }
                }
            });
        }

        function fetchTelemetryData() {
            if (selectedDrivers.size === 0) {
                initChart();
                return;
            }

            document.getElementById('telemetryStatus').innerText = "⏳ Fetching car_data telemetry...";

            fetch('/get_telemetry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_key: currentSessionKey,
                    driver_numbers: Array.from(selectedDrivers)
                })
            })
            .then(res => res.json())
            .then(data => {
                document.getElementById('telemetryStatus').innerText = "Live Telemetry Loaded";

                const datasets = [];
                let maxSamples = 0;

                Object.keys(data.telemetry).forEach(dNum => {
                    const t = data.telemetry[dNum];
                    if (t.sample_count > maxSamples) maxSamples = t.sample_count;

                    // Match driver color
                    let dColor = '#00E1D9';
                    Object.values(driverColorMap).forEach(info => {
                        if (info.num == dNum) dColor = info.color;
                    });

                    datasets.push({
                        label: `Driver #${dNum}`,
                        data: t.speeds,
                        borderColor: dColor,
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.2
                    });
                });

                chartInstance.data.labels = Array.from({ length: maxSamples }, (_, i) => i);
                chartInstance.data.datasets = datasets;
                chartInstance.update();
            });
        }
    </script>

</body>
</html>
"""

@app.route('/season_2026')
def season_2026():
    # 1. Fetch all 2026 sessions & meetings metadata
    sessions_res = requests.get(f"{BASE_URL}/sessions?year=2026&session_name=Race").json()
    meetings_res = requests.get(f"{BASE_URL}/meetings?year=2026").json()

    if not isinstance(sessions_res, list):
        return render_template_string(SEASON_2026_LAYOUT, races=[])

    # Build a lookup dictionary for circuit image URLs by meeting_key
    meetings_map = {}
    if isinstance(meetings_res, list):
        for m in meetings_res:
            m_key = m.get('meeting_key')
            meetings_map[m_key] = m.get('circuit_image')

    races_summary = []

    for s in sessions_res:
        s_key = s.get('session_key')
        m_key = s.get('meeting_key')
        location = s.get('location', 'Grand Prix')
        date_str = s.get('date_start', '')[:10]
        circuit_img = meetings_map.get(m_key, '')

        # Query results & drivers for this race
        try:
            results = requests.get(f"{BASE_URL}/session_result?session_key={s_key}").json()
            drivers = requests.get(f"{BASE_URL}/drivers?session_key={s_key}").json()

            d_map = {}
            if isinstance(drivers, list):
                d_map = {d.get('driver_number'): {
                    'name': d.get('broadcast_name', d.get('name_acronym', 'UNK')),
                    'color': f"#{d.get('team_colour', 'FFFFFF')}",
                    'team': d.get('team_name', '')
                } for d in drivers}

            # Grab P1, P2, P3
            podium = []
            if isinstance(results, list):
                sorted_res = sorted(results, key=lambda x: x.get('position') if (x.get('position') is not None and str(x.get('position')).isdigit()) else 99)
                for r in sorted_res[:3]:
                    num = r.get('driver_number')
                    info = d_map.get(num, {'name': 'UNK', 'color': '#fff', 'team': ''})
                    podium.append({
                        'pos': f"P{r.get('position')}",
                        'driver': info['name'],
                        'team': info['team'],
                        'color': info['color']
                    })

            if podium:
                races_summary.append({
                    'location': location,
                    'date': date_str,
                    'circuit_image': circuit_img,
                    'podium': podium
                })
        except Exception:
            continue

    return render_template_string(SEASON_2026_LAYOUT, races=races_summary)

if __name__ == '__main__':
    url = "http://127.0.0.1:8080/"
    Timer(0.5, lambda: webbrowser.open(url)).start()
    app.run(debug=True, host='127.0.0.1', port=8080)
