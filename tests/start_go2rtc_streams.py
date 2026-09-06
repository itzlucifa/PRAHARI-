import urllib.request
import json
import time

# Start streams via go2rtc API
for cam in ['camera-01', 'camera-02', 'camera-03']:
    try:
        req = urllib.request.Request(f'http://127.0.0.1:1984/api/start?src={cam}', method='POST')
        r = urllib.request.urlopen(req, timeout=5)
        print(f'Started {cam}: {r.status}')
    except Exception as e:
        print(f'Start {cam} error: {e}')

time.sleep(3)

# Check status
r = urllib.request.urlopen('http://127.0.0.1:1984/api/streams', timeout=5)
data = json.loads(r.read())
for name, info in data.items():
    print(f'{name}: producers={info.get("producers")}, consumers={info.get("consumers")}')
