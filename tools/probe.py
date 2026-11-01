import json, re, urllib.request
B = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
     'Accept': 'application/json, text/html;q=0.9, */*;q=0.8', 'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=B), timeout=25) as r:
        return r.read().decode('utf-8', 'replace')
out = {}
def keys(o, d=0, path=''):
    res = []
    if d > 4: return res
    if isinstance(o, dict):
        for k, v in o.items():
            res.append(f"{path}/{k}:{type(v).__name__}{'['+str(len(v))+']' if isinstance(v,(list,dict)) else ''}")
            res += keys(v, d+1, path+'/'+k)
    elif isinstance(o, list) and o:
        res += keys(o[0], d+1, path+'[0]')
    return res
# ACB
try:
    h = get('https://live.acb.com/es/partidos/ucam-murcia-vs-ilerna-lleida-105421/estadisticas')
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    if m:
        j = json.loads(m.group(1)); out['acb_next_keys'] = keys(j)[:150]
        s = json.dumps(j); i = s.find('Falk'); out['acb_falk_ctx'] = s[max(0,i-800):i+800]
    else:
        out['acb_scripts'] = re.findall(r'<script[^>]*src="([^"]+)"', h)[:20]
        i = h.find('Falk'); out['acb_falk_html'] = h[max(0,i-1500):i+1500]
        out['acb_api_hints'] = sorted(set(re.findall(r'https://[a-z0-9.-]*acb[a-z0-9.-]*/[^"\' ]{0,80}', h)))[:40]
except Exception as e: out['acb_err'] = str(e)
# FEB
try:
    h = get('https://competiciones.feb.es/estadisticas/partido/2487762')
    i = h.find('<table'); out['feb_partido_table'] = re.sub(r'\s+', ' ', h[i:i+4000])
    out['feb_title'] = re.findall(r'<title>(.*?)</title>', h, re.S)[:1]
except Exception as e: out['feb_err'] = str(e)
try:
    h = get('https://baloncestoenvivo.feb.es/resultados/primerafeb/1/2026')
    out['feb_links'] = sorted(set(re.findall(r'href="([^"]*(?:partido|Partido)[^"]*)"', h)))[:30]
    out['feb_result_text'] = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h))[:2500]
except Exception as e: out['feb2_err'] = str(e)
# EuroLeague
try:
    j = json.loads(get('https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games?teamCode=VIR'))
    g = j['data'][0]; out['el_game_keys'] = keys(g)[:80]
    out['el_games'] = [(x.get('gameCode'), x.get('date'), x.get('local', {}).get('club', {}).get('name'), x.get('road', {}).get('club', {}).get('name')) for x in j['data'][:8]]
except Exception as e: out['el_err'] = str(e)
try:
    b = json.loads(get('https://live.euroleague.net/api/Boxscore?gamecode=1&seasoncode=E2026'))
    out['el_box_keys'] = keys(b)[:60]
except Exception as e: out['el_box_err'] = str(e)
# BBL
try:
    h = get('https://www.easycredit-bbl.de/spielplan')
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    out['bbl_next'] = keys(json.loads(m.group(1)))[:80] if m else 'no next data'
    out['bbl_api_hints'] = sorted(set(re.findall(r'https://[a-z0-9.-]+/[^"\' ]{0,60}api[^"\' ]{0,60}', h)))[:30]
    out['bbl_game_links'] = sorted(set(re.findall(r'href="(/[^"]*spiel[^"]*)"', h)))[:15]
except Exception as e: out['bbl_err'] = str(e)
# LKL
try:
    h = get('https://www.lkl.lt/')
    out['lkl_links'] = sorted(set(re.findall(r'href="([^"]*(?:rungtyn|game|match)[^"]*)"', h)))[:20]
except Exception as e: out['lkl_err'] = str(e)
json.dump(out, open('data/_probe.json', 'w'), indent=1, ensure_ascii=False)
