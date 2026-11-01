import json, re, urllib.request
B = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36', 'Accept': 'text/html'}
out = {}
for slug in ['segundafeb', 'segunda', 'ligaebaplata', 'lebplata']:
    for g in range(1, 9):
        u = f'https://baloncestoenvivo.feb.es/resultados/{slug}/{g}/2026'
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=B), timeout=20) as r:
                h = r.read().decode('utf-8', 'replace')
            out[u] = {'n_games': len(re.findall(r'Partido\.aspx\?p=\d+', h)), 'sant': 'SANT ANTONI' in h.upper(), 'oct31': h.count('31/10/2026')}
        except Exception as e:
            out[u] = str(e)[:60]
try:
    with urllib.request.urlopen(urllib.request.Request('https://baloncestoenvivo.feb.es/resultados.aspx', headers=B), timeout=20) as r:
        h = r.read().decode('utf-8', 'replace')
    out['links'] = sorted(set(re.findall(r'href="([^"]*resultados[^"]*)"', h)))[:60]
except Exception as e:
    out['links'] = str(e)
json.dump(out, open('data/_probe.json', 'w'), indent=1)
