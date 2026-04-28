import requests
import pandas as pd
import urllib3
from datetime import datetime, timedelta
import os
import json
import sys

urllib3.disable_warnings()

def fetch_logs_for_user(target_user, mgmt_server, username, password, export_path):
    os.makedirs(export_path, exist_ok=True)
    
    print("=" * 70, flush=True)
    print("Check Point SmartView API", flush=True)
    print("=" * 70, flush=True)
    
    session = requests.Session()
    session.verify = False
    
    api_url = f"https://{mgmt_server}:4434/web_api"
    
    # Login
    print("\n[1/4] Login...", flush=True)
    resp = session.post(f"{api_url}/login", json={
        "user": username,
        "password": password
    })
    
    data = resp.json()
    sid = data["sid"]
    
    headers = {
        "Content-Type": "application/json",
        "X-chkp-sid": sid
    }
    
    print("✓ Login OK", flush=True)
    
    all_logs = []

    print("\n[2/4] Fetching logs for last 30 days...", flush=True)
    
    payload = {
        "new-query": {
            "time-frame": "last-30-days",
            "filter": f'blade:"Mobile Access" AND user:"{target_user}" AND action:"Log"'
        }
    }
    
    resp = session.post(f"{api_url}/show-logs", headers=headers, json=payload)
    data = resp.json()
    
    if "query-id" not in data:
        print("❌ API ERROR:", flush=True)
        print(json.dumps(data, indent=2), flush=True)
        session.post(f"{api_url}/logout", headers=headers)
        return None
    
    query_id = data["query-id"]
    logs = data.get("logs", [])
    
    print(f"✓ Query ID: {query_id}", flush=True)
    print(f"✓ Initial logs (30 days): {len(logs)}", flush=True)
    
    all_logs.extend(logs)
    
    # Pagination для первого запроса
    while True:
        resp = session.post(
            f"{api_url}/show-logs",
            headers=headers,
            json={
                "query-id": query_id,
                "offset": len(all_logs)
            }
        )
        
        data = resp.json()
        logs = data.get("logs", [])
        
        if not logs:
            break
        
        all_logs.extend(logs)
        print(f"Loaded (30 days): {len(all_logs)}", flush=True)
    
    print("\n[3/4] Fetching today's logs...", flush=True)
    
    now = datetime.now()
    today_start = now.strftime("%Y-%m-%dT00:00:00Z")
    today_end = now.strftime("%Y-%m-%dT23:59:59Z")
    
    print(f"   Today range: {today_start} to {today_end}", flush=True)
    
    payload_today = {
        "new-query": {
            "start-time": today_start,
            "end-time": today_end,
            "filter": f'blade:"Mobile Access" AND user:"{target_user}" AND action:"Log"'
        }
    }
    
    try:
        resp = session.post(f"{api_url}/show-logs", headers=headers, json=payload_today)
        data = resp.json()
        
        if "query-id" in data:
            query_id_today = data["query-id"]
            today_logs = data.get("logs", [])
            
            print(f"✓ Today's logs found: {len(today_logs)}", flush=True)
            all_logs.extend(today_logs)
            
            while True:
                resp = session.post(
                    f"{api_url}/show-logs",
                    headers=headers,
                    json={
                        "query-id": query_id_today,
                        "offset": len(today_logs)
                    }
                )
                
                data = resp.json()
                logs = data.get("logs", [])
                
                if not logs:
                    break
                
                today_logs.extend(logs)
                all_logs.extend(logs)
                print(f"Loaded today: {len(today_logs)}", flush=True)
        else:
            print("⚠️ No logs found for today (API limitation - logs may appear later)", flush=True)
            
    except Exception as e:
        print(f"⚠️ Error fetching today's logs: {e}", flush=True)
    
    session.post(f"{api_url}/logout", headers=headers)
    
    if not all_logs:
        print("❌ No logs found", flush=True)
        return None
    
    print("\n[4/4] Saving results...", flush=True)
    
    unique_logs = []
    seen = set()
    for log in all_logs:
        log_id = f"{log.get('time', '')}_{log.get('action', '')}"
        if log_id not in seen:
            seen.add(log_id)
            unique_logs.append(log)
    
    print(f"Total unique records: {len(unique_logs)}", flush=True)
    
    df = pd.json_normalize(unique_logs)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = os.path.join(export_path, f"vpn_logs_{target_user}_{timestamp}.csv")
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    
    print("\n" + "=" * 70, flush=True)
    print("✓ DONE", flush=True)
    print("File:", filename, flush=True)
    print("Records:", len(df), flush=True)
    
    if "time" in df.columns and len(df) > 0:
        min_time = df["time"].min()
        max_time = df["time"].max()
        print("Period:", min_time, "→", max_time, flush=True)
        
        today_str = now.strftime("%Y-%m-%d")
        if today_str in max_time:
            print("✅ Today's logs are INCLUDED!", flush=True)
        else:
            print("⚠️ Today's logs are NOT available yet (API indexing delay)", flush=True)
    
    print("=" * 70, flush=True)
    
    return filename

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fetch_logs.py <username>", flush=True)
        sys.exit(1)
    
    target_user = sys.argv[1]
    export_path = '/app/logs'
    
    filename = fetch_logs_for_user(
        target_user,
        '10.10.18.2',
        'ymalorodenko',
        'K093m333',
        export_path
    )
    
    if filename:
        print(filename, flush=True)
        sys.exit(0)
    else:
        print("ERROR: Failed to fetch logs", flush=True)
        sys.exit(1)

