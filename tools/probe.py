import json, urllib.request, time
B = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
     'Accept': 'application/json, text/html;q=0.9, */*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9,es;q=0.8'}
URLS = {
 'sofascore_day': 'https://api.sofascore.com/api/v1/sport/basketball/scheduled-events/2026-10-31',
 'sofascore_www': 'https://www.sofascore.com/api/v1/sport/basketball/scheduled-events/2026-10-31',
 'acb_live_page': 'https://live.acb.com/es/partidos/ucam-murcia-vs-ilerna-lleida-105421/estadisticas',
 'acb_api_guess': 'https://api2.acb.com/api/matchdata/Result/boxscores?matchId=105421',
 'feb_partido': 'https://competiciones.feb.es/estadisticas/partido/2487762',
 'feb_envivo': 'https://baloncestoenvivo.feb.es/resultados/primerafeb/1/2026',
 'espn_league_list': 'https://site.api.espn.com/apis/site/v2/sports/basketball/leagues',
 'espn_fiba': 'https://site.api.espn.com/apis/site/v2/sports/basketball/fiba/scoreboard',
 'espn_spain': 'https://site.api.espn.com/apis/site/v2/sports/basketball/spanish-liga-acb/scoreboard',
 'bbl_site': 'https://www.easycredit-bbl.de/',
 'bbl_api_guess': 'https://api.easycredit-bbl.de/v1/matches?season=2026',
 'euroleague_header': 'https://live.euroleague.net/api/Header?gamecode=1&seasoncode=E2026',
 'euroleague_v2': 'https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games?teamCode=VIR',
 'flashscore': 'https://www.flashscore.com/basketball/spain/acb/results/',
 'realgm': 'https://basketball.realgm.com/international/league/4/Spanish-ACB/scores',
 'proballers': 'https://www.proballers.com/basketball/league/1/spain-liga-endesa/schedule',
 'lkl': 'https://www.lkl.lt/',
 'basketligan': 'https://basketligan.se/',
}
out = {}
for k, u in URLS.items():
    t0 = time.time()
    try:
        req = urllib.request.Request(u, headers=B)
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(400000).decode('utf-8', 'replace')
            out[k] = {'status': r.status, 'type': r.headers.get('content-type'), 'len': len(body), 'head': body[:300],
                      'has_fibalivestats': 'fibalivestats' in body, 'ms': int((time.time() - t0) * 1000)}
    except Exception as e:
        out[k] = {'error': f'{e.__class__.__name__}: {e}'[:200]}
json.dump(out, open('data/_probe.json', 'w'), indent=1, ensure_ascii=False)
