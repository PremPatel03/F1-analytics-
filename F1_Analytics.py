import requests

def fetch_user_selected_race():

    # Gather inputs from the user
    # Note: Case sensitivity matters for OpenF1 (e.g., "Belgium", "Race")
    year_input = input("Enter Year (e.g., 2026, 2025): ").strip()
    country_input = input("Enter Country Name (e.g., Belgium, Great Britain, Monaco): ").strip()
    session_input = input("Enter Session Type (e.g., Race, Qualifying, Sprint): ").strip()
    
    print("\nSearching OpenF1 database for matching keys...")
    
    # Query the /sessions endpoint using the user's parameters
    # This acts like a phone book to find our hidden numeric ID
    lookup_url = f"https://api.openf1.org/v1/sessions?year={year_input}&country_name={country_input}&session_name={session_input}"
    
    try:
        session_data = requests.get(lookup_url).json()
        
        # Check if the API returned an empty list (meaning no match was found)
        if not session_data:
            print(" No matching race found! Check your spelling (e.g., 'Great Britain' instead of 'UK').")
            return
            
        # Grab the first match found
        matched_session = session_data[0]
        session_key = matched_session['session_key']
        location = matched_session['location']
        
        print(f" Track Location: {location}")
        print(f" Retrieved Session ID Key: {session_key}\n")
        
    except Exception as e:
        print(f" Error talking to OpenF1 API: {e}")
        return

    
    # Fetch Driver Profiles (Names & Teams)
    drivers_url = f"https://api.openf1.org/v1/drivers?session_key={session_key}"
    drivers_data = requests.get(drivers_url).json()
    
    driver_lookup = {}
    for d in drivers_data:
        num = d.get('driver_number')
        driver_lookup[num] = {
            'acronym': d.get('name_acronym', 'UNK'),
            'team': d.get('team_name', 'Unknown Team')
        }

    # Get the Standings for that Session
    results_url = f"https://api.openf1.org/v1/session_result?session_key={session_key}"
    results_data = requests.get(results_url).json()
    
    if not results_data:
        print("⚠️ Session metadata exists, but final result standings data is empty for this weekend.")
        return

    # Sort positions, handling potential missing data safely
    sorted_standings = sorted(
        results_data, 
        key=lambda x: x.get('position') if x.get('position') is not None else 99
    )
    
    # Print out our sorted results table
    print(f"🏆 {year_input} {country_input} {session_input.upper()} RESULTS:")
    print(f"{'POS':<5} | {'DRIVER':<6} | {'TEAM'}")
    print("-" * 40)
    
    for row in sorted_standings:
        pos_val = row.get('position')
        position = f"P{pos_val}" if pos_val is not None else "N/A"
        driver_num = row.get('driver_number')
        
        profile = driver_lookup.get(driver_num, {'acronym': 'UNK', 'team': 'Unknown Team'})
        acronym = profile['acronym']
        team = profile['team']
        
        print(f"{position:<5} | {acronym:<6} | {team}")

if __name__ == "__main__":
    fetch_user_selected_race()
