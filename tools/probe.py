import json, re, urllib.request
B = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
     'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8', 'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=B), timeout=25) as r:
        return r.geturl(), r.read().decode('utf-8', 'replace')
txt = lambda h: re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S)))
out = {}
def tryit(k, f):
    try: out[k] = f()
    except Exception as e: out[k] = 'ERR ' + str(e)[:200]
def acb():
    u, h = get('https://live.acb.com/es/partidos/ucam-murcia-vs-ilerna-lleida-105421/estadisticas')
    t = txt(h); i = t.find('UCAM')
    rows = re.findall(r'<tr[^>]*playerRow[^>]*>(.*?)</tr>', h, re.S)
    first = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', rows[0], re.S)] if rows else None
    heads = [re.sub(r'<[^>]+>', '', c).strip() for c in re.findall(r'<th[^>]*>(.*?)</th>', h, re.S)][:40]
    return {'n_rows': len(rows), 'first_row': first, 'heads': heads, 'text_start': t[:1500]}
tryit('acb', acb)
tryit('acb_noslug', lambda: get('https://live.acb.com/es/partidos/x-105421/estadisticas')[0])
def acbcal():
    u, h = get('https://live.acb.com/es/calendario')
    return {'url': u, 'links': sorted(set(re.findall(r'href="(/es/partidos/[^"]+)"', h)))[:40]}
tryit('acb_cal', acbcal)
def feb():
    u, h = get('https://competiciones.feb.es/estadisticas/partido/2487762')
    t = txt(h); return t[t.find('Resultado') - 300 if 'Resultado' in t else 0:][:2500]
tryit('feb_partido_text', feb)
def febres():
    u, h = get('https://baloncestoenvivo.feb.es/resultados/primerafeb/1/2026')
    blocks = re.findall(r'(<[^>]*Partido\.aspx\?p=\d+[^>]*>.*?</a>)', h, re.S)[:6]
    i = h.find('Partido.aspx?p=2535770'); return {'ctx': re.sub(r'\s+', ' ', h[i-2500:i+600])}
tryit('feb_results_ctx', febres)
def febenvivo():
    u, h = get('https://baloncestoenvivo.feb.es/Partido.aspx?p=2535770')
    return {'url': u, 'text': txt(h)[:2000]}
tryit('feb_envivo_partido', febenvivo)
def lkl():
    u, h = get('https://lkl.lt/rungtynes/11612')
    return {'fls': sorted(set(re.findall(r'fibalivestats[^"\' ]+', h)))[:5], 'text': txt(h)[:600]}
tryit('lkl_game', lkl)
def bbl():
    out2 = {}
    for path in ['/de/spielplan', '/spiele', '/de/', '/']:
        try:
            u, h = get('https://www.easycredit-bbl.de' + path)
            out2[path] = {'url': u, 'links': sorted(set(re.findall(r'href="(/[^"]*(?:spiel|game|match)[^"]*)"', h)))[:10],
                          'api': sorted(set(re.findall(r'https://[a-z0-9.-]+\.[a-z]+/[^"\' ]{0,40}(?:api|graphql)[^"\' ]{0,40}', h)))[:10]}
        except Exception as e: out2[path] = 'ERR ' + str(e)[:100]
    return out2
tryit('bbl', bbl)
json.dump(out, open('data/_probe.json', 'w'), indent=1, ensure_ascii=False)
