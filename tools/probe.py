"""Probe sources from GitHub's servers: can the YouTube channel feeds (no key) be read from there?"""
import json, re, urllib.request
out = {}
for name, cid in [('Miami HEAT', 'UC8bZbiKoPNRi3taABIaFeBw'), ('NBA', 'UCWJ2lWNubArHWmf3FIHbfcQ')]:
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={cid}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'swedes-abroad/1.0'}), timeout=30) as r:
            x = r.read().decode('utf-8', 'replace')
        out[name] = {'status': r.status, 'entries': len(re.findall('<entry>', x)), 'first': re.findall(r'<entry>.*?<title>([^<]*)', x, re.S)[:3]}
    except Exception as e:
        out[name] = {'error': f'{e.__class__.__name__}: {e}'[:200]}
json.dump(out, open('data/_probe.json', 'w'), indent=1)
print(out)
