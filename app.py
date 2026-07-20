import requests
import webbrowser
from threading import Timer
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

BASE_URL = "https://api.openf1.org/v1"

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
            weather_summary = f" Air Temp: {latest_weather.get('air_temperature')}°C  |   Track Temp: {latest_weather.get('track_temperature')}°C  |   Rainfall: {is_raining}  |   Wind Speed: {latest_weather.get('wind_speed')} m/s"
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
    
    # 5. Get Standings & Interval Times Safely
    results_res = []
    try:
        results_res = requests.get(f"{BASE_URL}/session_result?session_key={session_key}").json()
        if not isinstance(results_res, list):
            results_res = []
    except Exception:
        pass
        
    output_rows = []
    if not results_res and driver_lookup:
        for num, profile in driver_lookup.items():
            output_rows.append({
                "position": "N/A",
                "acronym": profile['acronym'],
                "team": profile['team'],
                "color": f"#{profile['color']}",
                "interval": "-",
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
            profile = driver_lookup.get(driver_num, {'acronym': 'UNK', 'team': 'Unknown Team', 'color': 'FFFFFF'})
            
            if i == 0:
                interval_str = "Leader"
            else:
                gap_val = row.get('time_diff_to_next') or row.get('gap_to_leader')
                if gap_val is not None:
                    interval_str = f"+{gap_val}s" if isinstance(gap_val, (int, float)) else str(gap_val)
                else:
                    interval_str = "+0.000s"
            
            output_rows.append({
                "position": f"P{p_val}" if p_val is not None else "N/A",
                "acronym": profile['acronym'],
                "team": profile['team'],
                "color": f"#{profile['color']}",
                "interval": interval_str,
                "radio_url": radio_lookup.get(driver_num, None)
            })
        
    return jsonify({
        "location": location,
        "session_name": actual_session_name,
        "year": year,
        "weather": weather_summary,
        "results": output_rows
    })

HTML_LAYOUT = """
<!DOCTYPE html>
<html>
<head>
    <title>F1 Analytics</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #111214; color: white; margin: 0; display: flex; flex-direction: column; min-height: 100vh; overflow-x: hidden; }
        
        /* Fixed Header Navigation */
        header { background: #1f2125; padding: 15px 40px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2e3137; box-shadow: 0 4px 10px rgba(0,0,0,0.2); position: sticky; top: 0; z-index: 1000; }
        h1 { font-size: 20px; margin: 0; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; color: #fff; }
        h1 span { color: #e10600; }
        .search-box { display: flex; gap: 10px; }
        select, button { padding: 10px 14px; border: none; border-radius: 4px; background: #2f333d; color: white; font-size: 14px; outline: none; }
        select { cursor: pointer; min-width: 140px; }
        button { background: #e10600; font-weight: bold; cursor: pointer; transition: 0.2s; padding: 10px 20px; }
        button:hover { background: #b80500; }
        
        /* Global Page Constraints */
        .page-content { width: 100%; max-width: 1400px; margin: 0 auto; padding: 30px 40px; display: flex; flex-direction: column; gap: 40px; }
        
        /* Headline Header Frame */
        .headline-card { background: #1a1b1e; border: 1px solid #2e3137; border-radius: 8px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); }
        .weather-banner { background: #18282c; padding: 15px 20px; border-radius: 6px; font-size: 14px; color: #00E1D9; border-left: 4px solid #00E1D9; font-weight: 500; margin-top: 15px; }
        
        /* Section Content Containers */
        .section-wrapper { background: #1a1b1e; border: 1px solid #2e3137; border-radius: 8px; padding: 25px; box-shadow: 0 4px 15px rgba(0,0,0,0.15); width: 100%; }
        .section-title { font-size: 14px; font-weight: 700; text-transform: uppercase; color: #888; margin-bottom: 20px; letter-spacing: 1px; border-bottom: 1px solid #2e3137; padding-bottom: 10px; }
        
        /* Table Layout Configuration: FIXED CUTOFF */
        table { width: 100%; border-collapse: collapse; }
        th, td { text-align: left; padding: 14px 20px; border-bottom: 1px solid #25272c; vertical-align: middle; }
        th { color: #555; text-transform: uppercase; font-size: 11px; font-weight: bold; letter-spacing: 0.5px; background: #1a1b1e; }
        
        /* Allocated Column Adjustments preventing compression clip points */
        th:nth-child(1), td:nth-child(1) { width: 90px; font-size: 15px; } /* Expanded Position lane */
        th:nth-child(2), td:nth-child(2) { width: 100px; } /* Driver Acronym */
        th:nth-child(3), td:nth-child(3) { width: 35%; }   /* Team stretch allocation */
        th:nth-child(4), td:nth-child(4) { width: 15%; }   /* Interval data text column */
        th:nth-child(5), td:nth-child(5) { width: 180px; }  /* Native audio layout space */

        tr:hover { background: #22242a; }
        
        /* Team Badge Stretch Wrapper */
        .team-container { display: flex; align-items: stretch; }
        .team-badge { border-left: 4px solid; padding-left: 12px; display: inline-flex; align-items: center; font-weight: 500; }
        
        audio { height: 26px; width: 150px; }

        /* Bottom Row Side-by-Side Analytics Section Grid */
        .analytics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-bottom: 40px; }
        .placeholder-card { background: #1a1b1e; border: 1px dashed #3e424c; border-radius: 8px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #5e6473; font-size: 14px; text-align: center; padding: 60px 20px; min-height: 400px; }
        .placeholder-card span { font-size: 32px; margin-bottom: 15px; }
    </style>
</head>
<body>

    <!-- STICKY HEADER FIXED NAVIGATION -->
    <header>
        <h1><span>F1</span> Analytics</h1>
        <div class="search-box">
            <select id="year"></select>
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
        
        <!-- SECTION 1: FULL SCREEN WIDTH LEADERBOARD -->
        <div class="section-wrapper">
            <div class="section-title">Official Session Leaderboard</div>
            <table>
                <thead>
                    <tr><th>Position</th><th>Driver</th><th>Constructor Team</th><th>Interval Gap</th><th> Team Radio Feed</th></tr>
                </thead>
                <tbody id="resultsTableBody">
                    <tr><td colspan="5" style="text-align:center; color:#555; padding: 60px;">Select filters above and hit search to load data rows.</td></tr>
                </tbody>
            </table>
        </div>
        
        <!-- SECTION 2: DOWNWARD SCROLL ANALYTICS GRID CONTENT PLACEHOLDERS -->
        <div class="analytics-grid">
            <div class="section-wrapper" style="padding:0; border:none; background:none;">
                <div class="section-title" style="margin-bottom:15px;">Telemetry Data</div>
                <div class="placeholder-card">
                    <span></span>
                    <b>Car Telemetry Data </b>
                    <p style="margin: 5px 0 0 0; font-size:12px; max-width:280px; color:#666;">This canvas zone is reserved for plotting Speed vs Throttle curves matching selected drivers.</p>
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
        window.addEventListener('DOMContentLoaded', () => {
            const yearSelect = document.getElementById('year');
            const startYear = 2023;
            const currentYear = 2026; 

            for (let year = currentYear; year >= startYear; year--) {
                const option = document.createElement('option');
                option.value = year;
                option.innerText = year;
                if (year === 2023) option.selected = true;
                yearSelect.appendChild(option);
            }
        });

        function searchRace() {
            const tableBody = document.getElementById('resultsTableBody');
            tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#888; padding: 60px;">⏳ Accessing OpenF1 active data stream arrays...</td></tr>`;

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
                    tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#e10600; padding: 60px;"> Error: ${data.error}</td></tr>`;
                    return;
                }
                
                document.getElementById('summaryTitle').innerText = `${data.year} ${data.location} Grand Prix`;
                document.getElementById('summarySubtitle').innerText = `Official Session Format Record: ${data.session_name}`;
                
                const weatherBanner = document.getElementById('weatherContainer');
                weatherBanner.innerText = data.weather;
                weatherBanner.style.display = 'block';
                
                tableBody.innerHTML = "";
                
                data.results.forEach(driver => {
                    const radioCell = driver.radio_url 
                        ? `<audio controls src="${driver.radio_url}"></audio>` 
                        : `<span style="color:#444; font-size:11px;">No Audio</span>`;

                    const row = `<tr>
                        <td><b style="color:#fff;">${driver.position}</b></td>
                        <td><b style="color:#fff; background:#22252c; padding:4px 8px; border-radius:4px;">${driver.acronym}</b></td>
                        <td>
                            <div class="team-container">
                                <span class="team-badge" style="border-color: ${driver.color}; color:#aaa;">${driver.team}</span>
                            </div>
                        </td>
                        <td style="color:#00E1D9; font-weight:600; font-size:13px; letter-spacing:0.5px;">${driver.interval}</td>
                        <td>${radioCell}</td>
                    </tr>`;
                    tableBody.innerHTML += row;
                });
            })
            .catch(err => {
                alert("An error occurred while communicating with the data server.");
                tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#e10600; padding: 60px;"> Connection Failed</td></tr>`;
            });
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    url = "http://127.0.0.1:8080/"
    Timer(0.5, lambda: webbrowser.open(url)).start()
    app.run(debug=True, host='127.0.0.1', port=8080)