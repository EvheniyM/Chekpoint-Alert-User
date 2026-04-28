import csv
from datetime import datetime, timedelta
import os
import sys
import glob
import pytz

KYIV_TZ = pytz.timezone('Europe/Kyiv')

def parse_date(ds):
    if not ds:
        return None
    try:
        if 'T' in ds:
            ds = ds.replace('Z', '')
            dt_utc = datetime.fromisoformat(ds)
            dt_utc = pytz.UTC.localize(dt_utc)
            return dt_utc.astimezone(KYIV_TZ)
    except:
        return None

def parse_logs(in_file, out_file):
    if not os.path.exists(in_file):
        pat = in_file.replace('.csv', '*.csv')
        fs = glob.glob(pat)
        if fs:
            in_file = max(fs, key=os.path.getctime)
        else:
            return False

    logins = []
    logouts = []
    now = datetime.now(KYIV_TZ)

    with open(in_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row.get('time', '')
            dt = parse_date(ts)
            if not dt or (now - dt).days > 30:
                continue
            action = row.get('action', '').strip()
            if action == 'Log In':
                logins.append(dt)
            elif action == 'Log Out':
                logouts.append(dt)

    logins.sort()
    logouts.sort()

    sessions = []
    used_logouts = set()
    for login in logins:
        for i, lo in enumerate(logouts):
            if i in used_logouts:
                continue
            if lo > login:
                dur = int((lo - login).total_seconds())
                if 60 <= dur <= 86400:
                    sessions.append({
                        'date': login.strftime('%d.%m.%Y'),
                        'time': f"{login.strftime('%H:%M:%S')} - {lo.strftime('%H:%M:%S')}",
                        'type': 'VPN Session',
                        'duration': f"{dur//3600:02d}:{(dur%3600)//60:02d}:{dur%60:02d}",
                        'sort_key': login
                    })
                    used_logouts.add(i)
                break

    sessions.sort(key=lambda x: x['sort_key'], reverse=True)

    with open(out_file, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Date', 'Time', 'Event Type', 'Duration'])
        for s in sessions:
            writer.writerow([s['date'], s['time'], s['type'], s['duration']])

    print(f"Saved {len(sessions)} sessions to {out_file}")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python parse_logs.py <username>")
        sys.exit(1)

    username = sys.argv[1]
    pattern = f"/app/logs/vpn_logs_{username}_*.csv"
    files = glob.glob(pattern)
    if not files:
        print(f"No log file for {username}")
        sys.exit(1)

    infile = max(files, key=os.path.getctime)
    outfile = f"/app/logs/{username}.csv"

    if parse_logs(infile, outfile):
        print(outfile)
    else:
        print("ERROR")
        sys.exit(1)

