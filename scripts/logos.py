"""Team logos for the crests on the site.

Collects every team name the site shows (schedule, team form, full box scores, coach games),
matches it to a team in a public team list (ESPN for the NBA and men's college basketball,
the EuroLeague feed for EuroLeague and EuroCup clubs), and copies the logo into logos/<slug>.png
at 128 px (128 colours, to keep the files small). data/logos.json maps each team name to its file. Teams that don't match keep the
coloured initials. Run by hand; it only adds logos that are missing.
"""
import io, json, os, re, sys, unicodedata, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'logos')
UA = {'User-Agent': 'swedes-abroad-logos/1.0'}


def get(url, raw=False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        b = r.read()
    return b if raw else json.loads(b)


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def slug(s):
    return norm(s).replace(' ', '-')


def our_teams():
    names = set()
    def add(v):
        if v and v not in ('—', 'TBC', 'placeholder'):
            names.add(v)
    for fn, keys in [('schedule', ['team', 'opponent']), ('teamform', ['team', 'opponent']), ('fullbox', ['team']), ('coachgames', ['team', 'opponent']), ('teams', ['team']), ('players', ['club']), ('sblgames', ['team', 'opponent']), ('gamelogs', ['team', 'opponent'])]:
        p = os.path.join(DATA, fn + '.json')
        if not os.path.exists(p):
            continue
        for r in json.load(open(p, encoding='utf-8')):
            if isinstance(r, dict):
                for k in keys:
                    add(r.get(k))
    return sorted(names)


def sources():
    """[(set of name keys, logo url, source)] from the public team lists."""
    out = []
    try:
        for t in get('https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams')['sports'][0]['leagues'][0]['teams']:
            t = t['team']
            keys = {norm(t['displayName']), norm(t.get('shortDisplayName')), norm(t.get('nickname'))}
            if t.get('logos'):
                out.append((keys, t['logos'][0]['href'], 'NBA (ESPN)', 'nba'))
    except Exception as e:
        print('NBA list failed:', e)
    try:
        for t in get('https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams?limit=1000')['sports'][0]['leagues'][0]['teams']:
            t = t['team']
            keys = {norm(t['displayName']), norm(t.get('location')), norm(t.get('shortDisplayName'))}
            if t.get('logos'):
                out.append((keys, t['logos'][0]['href'], 'NCAA (ESPN)', 'ncaa'))
    except Exception as e:
        print('NCAA list failed:', e)
    for comp in ('E', 'U'):
        for season in ('2026', '2025'):
            try:
                d = get(f'https://api-live.euroleague.net/v2/competitions/{comp}/seasons/{comp}{season}/clubs')['data']
            except Exception:
                continue
            for c in d:
                img = (c.get('images') or {}).get('crest')
                if img:
                    keys = {norm(c.get(k)) for k in ('name', 'abbreviatedName', 'clubPermanentName', 'editorialName', 'clubPermanentAlias', 'sponsor')}
                    out.append((keys - {''}, img, 'EuroLeague' if comp == 'E' else 'EuroCup', 'euro'))
            break
    return out


def league_pages():
    """Logos from the leagues' own sites: their team lists, the match pages the live updater already reads,
    and the FIBA LiveStats feeds for games we track. Returns [(set of name keys, logo url, source, 'euro')]."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import html as H
    import sources, update as U
    out = []
    def imgs(url, label, base=''):
        try:
            h = sources.page(url)
        except Exception as e:
            print('  could not read', url, str(e)[:80]); return
        n0 = len(out)
        for tag in re.findall(r'<img[^>]+>', h):
            alt = re.search(r'(?:alt|title)="([^"]+)"', tag); src = re.search(r'\s(?:src|data-src)="([^"]+)"', tag)
            if not alt or not src: continue
            u = H.unescape(src.group(1))
            if u.startswith('//'): u = 'https:' + u
            elif u.startswith('/'): u = base + u
            if not u.startswith('http') or re.search(r'sponsor|patro|partner|banner', u, re.I): continue
            out.append(({norm(H.unescape(alt.group(1)))}, u, label, 'euro'))
        print(' ', label, url, len(out) - n0, 'images')
    imgs('https://www.aba-liga.com/teams/', 'ABA League (aba-liga.com)', 'https://www.aba-liga.com')
    imgs('https://plk.pl/druzyny', 'Orlen Basket Liga (plk.pl)', 'https://plk.pl')
    imgs('https://lkl.lt/komandos', 'LKL (lkl.lt)', 'https://lkl.lt')
    imgs('https://www.championsleague.basketball/en/teams', 'Champions League (championsleague.basketball)')
    sched = json.load(open(os.path.join(DATA, 'schedule.json'), encoding='utf-8'))
    cg = os.path.join(DATA, 'coachgames.json')  # coaches' games too (Riipinen's Oradea)
    sched += json.load(open(cg, encoding='utf-8')) if os.path.exists(cg) else []
    for r in sched:
        f = str(r.get('live_feed') or '')
        kind, _, gid = f.partition(':')
        try:
            if kind == 'fiba':
                d = U.get(f'https://fibalivestats.dcd.shared.geniussports.com/data/{gid}/data.json')
                for t in (d.get('tm') or {}).values():
                    lg = (t.get('logoS') or {}).get('url') if isinstance(t.get('logoS'), dict) else None
                    if lg:
                        out.append(({norm(t.get('name')), norm(t.get('shortName'))} - {''}, lg, 'FIBA LiveStats', 'euro'))
            elif kind == 'acb':
                imgs(f'https://live.acb.com/es/partidos/x-{gid}/estadisticas', 'Liga ACB (acb.com)', 'https://live.acb.com')
            elif kind == 'feb':
                imgs(f'https://baloncestoenvivo.feb.es/partido/{gid}', 'FEB (feb.es)', 'https://baloncestoenvivo.feb.es')
            elif kind == 'bbl':
                imgs(f'https://www.easycredit-bbl.de/spiele/{gid}', 'easyCredit BBL', 'https://www.easycredit-bbl.de')
            elif kind == 'lba':
                imgs(f'https://www.legabasket.it/game/{gid}/x', 'LBA (legabasket.it)', 'https://www.legabasket.it')
            elif kind == 'aba':
                imgs(f'https://www.aba-liga.com/match/{gid}/Overview/q1/1/home/x/', 'ABA League (aba-liga.com)', 'https://www.aba-liga.com')
        except Exception as e:
            print('  feed', f, str(e)[:80])
    # Iceland (and any league on Genius Sports' hosted pages): the team logos on our clubs' schedule pages,
    # named by the team-name link next to them; our club also under the site's spelling
    try:
        import schedule_eu as E
        for club, (org, cid, tid, tz, comp) in E.GENIUS_TEAMS.items():
            h = sources.page(f'https://hosted.dcd.shared.geniussports.com/{org}/en/competition/{cid}/team/{tid}/schedule')
            n0 = len(out)
            for tid2, src, alt in re.findall(r'team/(\d+)/[^"]*"\s+title="[^"]*"><img src\s*=\s*"([^"]+)"\s+alt="([^"]+)"', h):
                keys = {norm(alt)} | ({norm(club)} if tid2 == str(tid) else set())
                out.append((keys, src, f'{comp} (Genius Sports)', 'euro'))
            print('  Genius', club, len(out) - n0, 'logos')
    except Exception as e:
        print('  Genius', str(e)[:80])
    # Norway (BLNO): the federation's API has each club's logo (base64 PNG), under the club's team names
    try:
        import base64, tempfile
        import schedule_eu as E
        seen = set()
        for club, (tour, short) in E.NIF_TEAMS.items():
            for m in (sources.nif_get(f'ta/TournamentMatches/?tournamentId={tour}') or {}).get('matches') or []:
                for side in ('home', 'away'):
                    oid = m.get(side + 'teamClubOrgId')
                    if not oid or oid in seen:
                        continue
                    seen.add(oid)
                    org = (sources.nif_get(f'org/Organisation?orgIds={oid}') or [{}])[0]
                    b64 = org.get('orgLogoBase64')
                    if not b64:
                        continue
                    f = tempfile.NamedTemporaryFile(suffix='.png', delete=False); f.write(base64.b64decode(b64)); f.close()
                    nm = sources.nif_team(m.get(side + 'team'))
                    keys = {norm(nm), norm(m.get(side + 'teamOrgName')), norm(org.get('orgName'))} - {''}
                    if nm == short:
                        keys.add(norm(club))
                    out.append((keys, 'file://' + f.name, 'Norwegian federation (basket.no)', 'euro'))
        print('  BLNO', len(seen), 'clubs')
    except Exception as e:
        print('  BLNO', str(e)[:80])
    # ProA/ProB: the live ticker's /init/<game> names both teams, the crest is pics2/<season>/lo/<team id>.
    # Walk our clubs' season calendars until no new team turns up (one league, so that's soon).
    try:
        import schedule_eu as E
        seen, quiet = {}, 0
        for f in E.prob():
            gid = f['feed'].split(':', 1)[1]
            d = U.get(f'https://live.2basketballbundesliga.de/init/{gid}')
            season = str((d.get('game') or {}).get('season') or '').replace('/', '_')
            new = 0
            for t, ours in ((d.get('teamA') or {}, f['home']), (d.get('teamB') or {}, f['away'])):
                if t.get('id') and t['id'] not in seen:
                    seen[t['id']] = 1; new += 1
                    out.append(({norm(t.get('caption')), norm(ours)} - {''}, f'https://api.2basketballbundesliga.de/pics2/{season}/lo/{t["id"]}',
                                '2. Basketball-Bundesliga', 'euro'))
            quiet = 0 if new else quiet + 1
            if quiet >= 8:
                break
        print('  ProB', len(seen), 'teams')
    except Exception as e:
        print('  ProB', str(e)[:80])
    return out


def match(name, src):
    n = norm(name)
    hits = [s for s in src if n in s[0]]
    if hits:
        return hits[0]
    # 'Miami Heat' vs 'Heat', 'Virtus Bologna' vs 'Virtus Segafredo Bologna': every word of ours in one of theirs
    words = set(n.split())
    strong = {w for w in words if len(w) > 3 and w not in {'basket', 'basketball', 'baskets', 'club', 'team'}}
    hits = [s for s in src if s[3] == 'euro' and any(k and (k in n or (strong and strong <= set(k.split()))) and len(k) > 3 for k in s[0])]
    if len({h[1] for h in hits}) == 1:
        return hits[0]
    if len(words) >= 2:
        hits = [s for s in src if s[3] == 'euro' and any(words <= set(k.split()) for k in s[0])]
        if len(hits) == 1:
            return hits[0]
    return None


# wrong matches found by eye (a different club's crest, or a sponsor's logo): never take these from the fuzzy match
SKIP = {'Fribourg Olympic', 'Unicaja', 'Tizona Burgos'}


def is_dark(path):
    """True when most of the logo has too little contrast with the site's navy (#071429) to be seen."""
    from PIL import Image
    def rl(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    lum = lambda p: 0.2126 * rl(p[0]) + 0.7152 * rl(p[1]) + 0.0722 * rl(p[2])
    bg = lum((7, 20, 41))
    px = [p for p in Image.open(path).convert('RGBA').getdata() if p[3] > 128]
    low = sum(1 for p in px if (lum(p) + 0.05) / (bg + 0.05) < 2.0)
    return bool(px) and low / len(px) > 0.5


def main():
    from PIL import Image
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(DATA, 'logos.json')
    have = {r['team']: r for r in json.load(open(path, encoding='utf-8'))} if os.path.exists(path) else {}
    src = sources()
    if '--leagues' in sys.argv:
        src += league_pages()
    print(len(src), 'teams in the public lists')
    added, missing = 0, []
    for name in our_teams():
        if name in have and os.path.exists(os.path.join(ROOT, have[name]['src'])):
            continue
        m = None if name in SKIP else match(name, src)
        if not m:
            missing.append(name)
            continue
        fn = 'logos/' + slug(name) + '.png'
        try:
            im = Image.open(io.BytesIO(get(m[1], raw=True))).convert('RGBA')
            im.thumbnail((128, 128))
            im.quantize(colors=128, method=Image.Quantize.FASTOCTREE).save(os.path.join(ROOT, fn), optimize=True)
        except Exception as e:
            print('could not fetch', name, e)
            missing.append(name)
            continue
        have[name] = {'team': name, 'src': fn, 'source': m[2], 'dark': is_dark(os.path.join(ROOT, fn))}
        added += 1
    json.dump(sorted(have.values(), key=lambda r: r['team']), open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'added {added}, total {len(have)}, no logo for {len(missing)}')
    print('no logo:', ', '.join(missing))


if __name__ == '__main__':
    main()
