#!/usr/bin/env python3
"""
Find FIBA LiveStats ids for upcoming games on their own, so they update live without anyone
looking them up. Games of one league round get ids close to each other, so for every game
without a "live_feed" we scan the ids around the last known id of the same competition
(data/feed_seeds.json) and match the two team names.

Run: python3 scripts/discover.py            (games from 6 h ago to 30 h ahead)
"""
import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

SEEDS = os.path.join(U.DATA, 'feed_seeds.json')
SPAN = 400


def fetch(fid):
    try:
        req = urllib.request.Request(f'https://fibalivestats.dcd.shared.geniussports.com/data/{fid}/data.json', headers=U.UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode('utf-8'))
        tm = d.get('tm') or {}
        return fid, [str((tm.get(k) or {}).get('name') or '') + ' ' + str((tm.get(k) or {}).get('nameInternational') or '') for k in ('1', '2')]
    except Exception:
        return fid, None


def words(s):
    return {w for w in U.norm(s).split() if len(w) > 2 and w not in {'basket', 'basketball', 'club', 'team', 'sport', 'enea', 'energa'}}


def words_or_short(s):
    # names like "KR Basket" have no long word left: fall back to the short ones ("kr")
    return words(s) or {w for w in U.norm(s).split() if w not in {'basket', 'basketball', 'club', 'team'}}


def match(names, row):
    a, b = words_or_short(row.get('team', '')), words_or_short(row.get('opponent', ''))
    n1, n2 = words_or_short(names[0]), words_or_short(names[1])
    return (a & n1 and b & n2) or (a & n2 and b & n1)


def main():
    seeds = json.load(open(SEEDS)) if os.path.exists(SEEDS) else {}
    sched, coach = U.load('schedule'), U.load('coachgames')
    now = U.now()
    todo = []
    for name, rows in (('schedule', sched), ('coachgames', coach)):
        for r in rows:
            if r.get('live_feed') or r.get('status') == 'final' or r.get('competition') in ('NBA', 'NCAA'):
                continue
            tip = U.tip_time(r)
            if tip and now - dt.timedelta(hours=6) <= tip <= now + dt.timedelta(hours=30) and r.get('competition') in seeds:
                todo.append(r)
    # Spanish leagues and the EuroLeague have their own free live pages
    import sources
    other = False
    for name, rows in (('schedule', sched), ('coachgames', coach)):
        for r in rows:
            if r.get('live_feed') or r.get('status') == 'final' and not r.get('backfill'):
                continue
            tip = U.tip_time(r)
            if not tip or not (now - dt.timedelta(hours=6) <= tip <= now + dt.timedelta(hours=30)) and not r.get('backfill'):
                continue
            comp = r.get('competition')
            try:
                f = None
                if comp in sources.FEB_COMP:
                    f = sources.find_feb(r)
                elif comp == 'Liga ACB' and seeds.get('Liga ACB'):
                    f = sources.find_acb(r, int(seeds['Liga ACB']))
                    if f:
                        seeds['Liga ACB'] = max(int(seeds['Liga ACB']), int(f.split(':')[1]))
                elif comp == 'EuroLeague':
                    f = sources.find_euroleague(r)
                if f:
                    r['live_feed'] = f
                    other = True
                    print(f"  {r['game_id']}: {comp} -> {f}")
            except Exception as e:
                print(f"  {r['game_id']}: lookup error {e}")
    if other:
        U.save('schedule', sched)
        U.save('coachgames', coach)
        json.dump(seeds, open(SEEDS, 'w'), indent=1)
        U.write_version(True)
    todo = [r for r in todo if not r.get('live_feed')]
    if not todo:
        print('nothing to look up'); return
    found = 0
    log = []
    by_comp = {}
    for r in todo:
        by_comp.setdefault(r['competition'], []).append(r)
    for comp, rows in by_comp.items():
        seed = int(seeds[comp])
        ids = [seed + k for k in range(-SPAN, SPAN) if k]
        with cf.ThreadPoolExecutor(24) as ex:
            res = {fid: n for fid, n in ex.map(fetch, ids) if n}
        log.append({'competition': comp, 'seed': seed, 'scanned': len(ids), 'answered': len(res),
                    'sample': sorted(((fid, n) for fid, n in res.items()), key=lambda x: abs(x[0] - seed))[:12]})
        for r in rows:
            hit = [fid for fid, n in res.items() if match(n, r)]
            if hit:
                fid = min(hit, key=lambda x: abs(x - seed))
                r['live_feed'] = f'fiba:{fid}'
                seeds[comp] = max(int(seeds[comp]), fid)
                found += 1
                print(f"  {r['game_id']}: {comp} {r.get('team')} - {r.get('opponent')} -> {fid}")
            else:
                print(f"  {r['game_id']}: no id found near {seed} for {r.get('team')} - {r.get('opponent')}")
    if found:
        U.save('schedule', sched)
        U.save('coachgames', coach)
        json.dump(seeds, open(SEEDS, 'w'), indent=1)
        U.write_version(True)
    json.dump({'at': U.now().isoformat(timespec='seconds'), 'found': found, 'log': log}, open(os.path.join(U.DATA, '_discover.json'), 'w'), ensure_ascii=False, indent=1)
    print('found', found)


if __name__ == '__main__':
    main()
