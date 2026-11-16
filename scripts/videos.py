#!/usr/bin/env python3
"""
Video highlights for NBA and college games (data/videos.json), from ESPN's public game summaries.
For each final NBA/NCAA game with an ESPN id from the last 3 days it keeps the full "Game Highlights" clip
and up to 5 more, clips that name one of the game's Swedes first. College clips often appear hours after the
game, so a game is checked again until it is 3 days old. The site links to ESPN to play them.

Run: python3 scripts/videos.py            (from the live job, once an hour; --force to run now)
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

PATH = os.path.join(U.DATA, 'videos.json')


def clips(sport, eid, swedes):
    d = U.get(f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/summary?event={eid}')
    out = []
    for v in d.get('videos') or []:
        url = ((v.get('links') or {}).get('web') or {}).get('href') or ''
        if not url.startswith('https://www.espn.com/') or not v.get('headline'):
            continue
        txt = U.norm(f"{v.get('headline', '')} {v.get('description', '')}")
        who = [n for n in swedes if U.norm(n) in txt]
        out.append(dict(title=v['headline'], secs=int(v.get('duration') or 0), thumb=v.get('thumbnail') or '', url=url,
                        full=bool(re.search(r'game highlights', v['headline'], re.I)), swedes=who))
    out.sort(key=lambda c: (not c['full'], not c['swedes']))
    return out[:6]


def main(argv):
    now = U.now()
    # once an hour (the live job runs every few minutes)
    if '--force' not in argv and now.minute >= 6:
        return 0
    try:
        have = json.load(open(PATH, encoding='utf-8'))
    except Exception:
        have = []
    by = {r['game_id']: r for r in have}
    lo = (now - dt.timedelta(days=int(os.environ.get('VDAYS', 3)))).date().isoformat()
    for r in U.load('schedule'):
        if r.get('status') != 'final' or r.get('competition') not in ('NBA', 'NCAA') or not r.get('espn_id') or (r.get('date') or '') < lo:
            continue
        sport = 'nba' if r['competition'] == 'NBA' else 'mens-college-basketball'
        try:
            c = clips(sport, r['espn_id'], [x.strip() for x in str(r.get('players') or '').split(',') if x.strip()])
        except Exception as e:
            print(f"  {r['game_id']}: {e.__class__.__name__}")
            continue
        if c and (r['game_id'] not in by or by[r['game_id']]['clips'] != c):
            by[r['game_id']] = dict(game_id=r['game_id'], date=r['date'], source='ESPN', clips=c)
            print(f"  {r['game_id']}: {len(c)} clips, {sum(1 for x in c if x['swedes'])} with a Swede")
    keep = sorted(by.values(), key=lambda r: r['date'])[-150:]
    if U.save('videos', keep):
        U.write_version(True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
