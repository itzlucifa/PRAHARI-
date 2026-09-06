import urllib.request
import json

r = urllib.request.urlopen("http://127.0.0.1:1984/api/streams", timeout=5)
data = json.loads(r.read())
for name, info in data.items():
    print(f"{name}: producers={info.get('producers')}, consumers={info.get('consumers')}")
