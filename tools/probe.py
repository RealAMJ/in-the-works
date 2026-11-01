import json, re, urllib.request, html
B = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36', 'Accept': 'text/html'}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=B), timeout=20) as r:
        return r.geturl(), r.read().decode('utf-8', 'replace')
out = {}
for u in ['https://baloncestoenvivo.feb.es/resultados.aspx?g=2&t=2026&nm=segundafeb', 'https://baloncestoenvivo.feb.es/resultados.aspx?g=1&t=2026']:
    try:
        url, h = get(u)
        opts = re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', h, re.S)
        out[u] = {'final_url': url, 'selects': {n: re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)</option>', o)[:30] for n, o in opts},
                  'sant': 'SANT ANTONI' in html.unescape(h).upper(), 'games': len(re.findall(r'Partido\.aspx\?p=\d+', h)),
                  'teams_sample': re.findall(r'Equipo\.aspx\?i=\d+">(.*?)</a>', h)[:6]}
    except Exception as e:
        out[u] = str(e)[:100]
json.dump(out, open('data/_probe.json', 'w'), indent=1, ensure_ascii=False)
