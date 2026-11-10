"""Photos and facts for SBL players, from the league's own player lists (sblherr.se).

Every club's squad comes from the league site's team pages (the same lists the clubs' own sites show). For each
player with a standout game in data/sbl.json (and anyone listed in data/sblplayers.json) the portrait is copied to
photos/sbl-<name>.webp, the face is found so it can be placed like everyone else's, and the player's number,
height and nationality go to data/sblroster.json. Run by hand; it only adds what is missing.
"""
import io, json, os, re, sys, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402
import sbl  # noqa: E402

SITE = 'https://www.sblherr.se'
STANDINGS = SITE + '/api/statistics-v2/stats-info/standings_standings?count=25&ssgtUuid=tshxzd8cqh&provider=genius-basketball'


def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=U.UA), timeout=40) as r:
        return r.read()


def teams():
    t = get(STANDINGS).decode()
    out = {}
    for m in re.finditer(r'"info":\{"type":"team","id":\d+,"name":"([^"]+)","uuid":"([^"]+)"', t):
        out[sbl.team_name(m.group(1))] = m.group(2)
    return out


def squad(uuid):
    rows = []
    for grp in json.loads(get(f'{SITE}/api/sports-v2/athletes/by-team-uuid/{uuid}')):
        for p in grp.get('players') or []:
            por = next((x.get('renderedMedia', {}).get('url') for x in (p.get('portraitList') or []) if x.get('renderedMedia')), None)
            rows.append(dict(name=p.get('fullName') or f"{p.get('firstName', '')} {p.get('lastName', '')}".strip(), first=p.get('firstName') or '', last=p.get('lastName') or '',
                             number=p.get('jerseyNumber'), height=p.get('height'), nationality=p.get('nationality'), position=grp.get('position'), portrait=por))
    return rows


def key(s):
    return re.sub(r'[^a-z]', '', U.norm(s))


def find(name, team, sq):
    name = {'Charles Barton': 'Charles Barton Jr'}.get(name, name)  # the squad list adds the Jr
    n = U.norm(name).split()
    for p in sq.get(team, []):
        if key(p['name']) == key(name):
            return p
    # same last name (with or without a hyphen) and the same first letter, on the same team
    hits = [p for p in sq.get(team, []) if key(p['last']) and (key(p['last']) == key(' '.join(n[1:])) or key(p['last']) == key(n[-1])) and U.norm(p['first'])[:1] == n[0][:1]]
    return hits[0] if len(hits) == 1 else None


def face_box(path):
    import cv2
    img = cv2.imread(path)
    if img is None:
        return None
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cas = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    f = cas.detectMultiScale(g, 1.1, 6, minSize=(30, 30))
    if not len(f):
        return None
    x, y, w, h = max(f, key=lambda r: r[2] * r[3])
    H, W = g.shape
    return [round(x / W, 4), round(y / H, 4), round(w / W, 4), round(h / H, 4)]


def main():
    from PIL import Image
    T = teams(); print(len(T), 'teams')
    sq = {t: squad(u) for t, u in T.items()}
    print(sum(len(v) for v in sq.values()), 'players on the squads')
    want = {}
    for r in U.load('sbl'):
        want.setdefault(r['player'], r['team'])
    for r in U.load('sblplayers'):
        want.setdefault(r['player'], sbl.team_name(r.get('club', '')))
    photos = U.load('photos'); have = {U.norm(p['player']) for p in photos}
    rp = os.path.join(U.DATA, 'sblroster.json'); roster = json.load(open(rp, encoding='utf-8')) if os.path.exists(rp) else []
    rkey = {U.norm(r['player']) for r in roster}
    added, missing = 0, []
    for name, team in sorted(want.items()):
        p = find(name, team, sq)
        if not p:
            missing.append(f'{name} ({team})'); continue
        if U.norm(name) not in rkey:
            roster.append(dict(player=name, team=team, number=p['number'], height=p['height'], nationality=p['nationality'], position=p['position'], league_name=p['name']))
            rkey.add(U.norm(name))
        if U.norm(name) in have or not p['portrait']:
            continue
        try:
            im = Image.open(io.BytesIO(get(p['portrait']))).convert('RGBA')
        except Exception as e:
            print('  photo', name, e.__class__.__name__); continue
        im.thumbnail((600, 800)); bg = im
        fn = 'photos/sbl-' + re.sub(r'[^a-z0-9]+', '-', U.norm(name)).strip('-') + '.webp'
        bg.save(os.path.join(U.ROOT, fn), 'WEBP', quality=82)
        fb = face_box(os.path.join(U.ROOT, fn))
        row = dict(player=name, src=fn, credit='', source='SBL (sblherr.se)')
        if fb:
            row['fbox'] = fb
        photos.append(row); have.add(U.norm(name)); added += 1
    U.save('photos', photos)
    roster.sort(key=lambda r: r['player'])
    json.dump(roster, open(rp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'{added} photos added, {len(roster)} players in sblroster.json')
    if missing:
        print('not found on the squads:', ', '.join(missing))


if __name__ == '__main__':
    main()
