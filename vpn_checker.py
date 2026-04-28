import requests
import urllib3
from datetime import datetime, timedelta
import json

urllib3.disable_warnings()

class VPNChecker:
    def __init__(self, server, username, password):
        self.server = server
        self.username = username
        self.password = password
        self.api_url = f"https://{server}:4434/web_api"
        self.session = requests.Session()
        self.session.verify = False
        self.sid = None
    
    def login(self):
        try:
            resp = self.session.post(f"{self.api_url}/login", json={
                "user": self.username,
                "password": self.password
            }, timeout=30)
            data = resp.json()
            if "sid" in data:
                self.sid = data["sid"]
                self.session.headers.update({"X-chkp-sid": self.sid})
                return True
            return False
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    def get_user_last_login(self, username):
        try:
            # Используем правильный фильтр - прямой поиск по user
            payload = {
                "new-query": {
                    "time-frame": "last-30-days",
                    "filter": f'blade:"Mobile Access" AND user:"{username}"'
                }
            }
            
            resp = self.session.post(f"{self.api_url}/show-logs", json=payload, timeout=60)
            data = resp.json()
            
            if "query-id" not in data:
                return None
            
            query_id = data["query-id"]
            all_logs = data.get("logs", [])
            
            # Пагинация
            offset = len(all_logs)
            while True:
                resp = self.session.post(f"{self.api_url}/show-logs", json={
                    "query-id": query_id,
                    "offset": offset
                }, timeout=60)
                data = resp.json()
                logs = data.get("logs", [])
                if not logs:
                    break
                all_logs.extend(logs)
                offset += len(logs)
            
            # Находим последний логин (Log In)
            last_login = None
            for log in all_logs:
                action = log.get('action', '')
                if action == 'Log In':
                    time_str = log.get('time', '')
                    if time_str:
                        try:
                            login_time = datetime.fromisoformat(time_str.replace('Z', ''))
                            if last_login is None or login_time > last_login:
                                last_login = login_time
                        except:
                            pass
            
            return last_login
                
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def logout(self):
        if self.sid:
            try:
                self.session.post(f"{self.api_url}/logout")
            except:
                pass
    
    def close(self):
        self.logout()
