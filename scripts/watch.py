#!/usr/bin/env python3
"""
The Video page's list (data/watch.json), rebuilt from three sources:
  * ESPN clips that name one of our Swedes (data/videos.json, from scripts/videos.py), as "Highlight"
  * interviews and team videos from the players' NBA.com profiles (NBA_IDS below); NBA.com doesn't let other
    sites play its videos, so these open on NBA.com
  * hand-picked YouTube videos (data/watch_extra.json) and the daily YouTube search (data/watch_yt.json)

Runs once an hour from the live job (--force to run now).
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

NBA_IDS = {'Pelle Larsson': 1641796}


def nba_videos(player, pid):
    req = urllib.request.Request(f'https://www.nba.com/player/{pid}', headers={'User-Agent': 'swedes-abroad/1.0', 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=30) as r:
        h = r.read().decode('utf-8', 'replace')
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    out, seen = [], set()

    def walk(o):
        if isinstance(o, dict):
            link = str(o.get('permalink') or '')
            if '/videos/' in link and o.get('title') and link not in seen:
                seen.add(link)
                d = o.get('duration') or '00:00:00'
                hh, mm, ss = ([0, 0] + [int(x) for x in str(d).split(':')])[-3:]
                title = str(o['title'])
                surname = player.split()[-1]
                kind = 'Interview' if (re.match(rf'^({re.escape(player.split()[0])}|{re.escape(surname)})\b.*\bon\b', title, re.I) or re.search(r'\b(interview|press|postgame|media)\b', title, re.I)) else 'Feature'
                out.append(dict(kind=kind, player=player, title=title, src='nba', url=link, thumb=o.get('featuredImage') or o.get('thumbnail') or '',
                                secs=hh * 3600 + mm * 60 + ss, date=str(o.get('date') or '')[:10], channel='NBA.com'))
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    if m:
        walk(json.loads(m.group(1)))
    return sorted(out, key=lambda x: x['date'], reverse=True)[:12]


def main(argv):
    now = U.now()
    if '--force' not in argv and now.minute >= 6:
        return 0
    items = []
    for g in U.load('videos'):
        for c in g.get('clips') or []:
            if c.get('swedes'):
                m = re.search(r'/id/(\d+)', c.get('url') or '')
                if m:
                    items.append(dict(kind='Highlight', player=c['swedes'][0], title=c['title'], src='espn', vid=m.group(1), thumb=c.get('thumb', ''),
                                      secs=c.get('secs', 0), date=g['date'], game_id=g['game_id']))
    try:
        old = json.load(open(os.path.join(U.DATA, 'watch.json'), encoding='utf-8'))
    except Exception:
        old = []
    for p, pid in NBA_IDS.items():
        try:
            items += nba_videos(p, pid)
        except Exception as e:  # NBA.com can refuse automated requests: keep what we had
            print(f'  NBA.com {p}: {e.__class__.__name__}')
            items += [x for x in old if x.get('src') == 'nba' and x.get('player') == p]
    for extra in ('watch_extra.json', 'watch_yt.json'):  # hand-picked, and the daily YouTube search (scripts/youtube.py)
        try:
            items += json.load(open(os.path.join(U.DATA, extra), encoding='utf-8'))
        except Exception:
            pass
    seen = set()
    items = [x for x in items if not (x.get('vid') and x['vid'] in seen) and not seen.add(x.get('vid') or id(x))]
    dated = sorted([x for x in items if x.get('date')], key=lambda x: x['date'], reverse=True)
    items = dated[:80] + [x for x in items if not x.get('date')]
    if U.save('watch', items):
        U.write_version(True)
        print(f'watch: {len(items)} videos')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
