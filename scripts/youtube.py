#!/usr/bin/env python3
"""
YouTube videos of the Swedes abroad (players and coaches) for the Video page, through the official
YouTube Data API (key in the YOUTUBE_API_KEY secret). Output: data/watch_yt.json, merged by scripts/watch.py.

Once a day it searches each person's full name in videos from the last 10 days and keeps a video only if
  * the full name is in the title (he is the subject of the video), and
  * the channel is official: his club, his league or a cup it plays, the national federation, a league
    or broadcaster we know (OFFICIAL below), or a club/college media outlet named after his club.
Fan compilations and re-uploads are left out. Videos YouTube doesn't allow on other sites open on YouTube.

Cost: about 100 units per person per day of YouTube's free 10,000 a day.
Run: python3 scripts/youtube.py
"""
import datetime as dt
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

API = 'https://www.googleapis.com/youtube/v3/'
PATH = os.path.join(U.DATA, 'watch_yt.json')
# official channels by their exact name (lower case); a club's own channel is matched by its name below
OFFICIAL = {'nba', 'miami heat', 'euroleague', 'euroleague basketball', 'acb', 'liga endesa', 'basketball champions league', 'fiba',
            'fiba basketball', 'fiba europe cup', 'svensk basket', 'basketligan', 'easycredit bbl', 'lkl', 'aba league', 'lega basket', 'lba',
            'orlen basket liga', 'primera feb', 'feb', 'espn', 'espn wichita', 'ncaa march madness', "big ten men's basketball", 'big ten network',
            'the wolverine: michigan football and basketball', 'the michigan insider', '12 news', 'eurohoops', 'basketnews', 'sportbladet', 'expressen',
            'aftonbladet', 'svt sport', 'tv4 sport', 'digi sport', 'nrk sport', 'rúv', 'ruv'}
FAN = re.compile(r'highlight|full play|fan|nation|polska|edits?\b|daily|vision|mixtape|hoops|ballin|talk|clips|hub|news\b(?!.*12)', re.I)


def plain(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s or '')) if not unicodedata.combining(c)).lower()


def get(path, **q):
    q['key'] = os.environ['YOUTUBE_API_KEY']
    with urllib.request.urlopen(urllib.request.Request(API + path + '?' + urllib.parse.urlencode(q), headers=U.UA), timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def words(s):
    return {w for w in re.sub(r'[^a-z0-9 ]', ' ', plain(s)).split() if len(w) > 2 and w not in {'basket', 'basketball', 'baloncesto', 'club', 'the', 'and', 'state', 'university'}}


def official(channel, club, leagues):
    c = plain(channel).strip()
    if c in OFFICIAL:
        return True
    if FAN.search(channel):
        return False
    base = re.sub(r'\s*[-|–]\s*(canal oficial|official|oficial|officiel|ufficiale)\s*$', '', c).strip()
    # the club's own channel: its name, or the club's distinctive words and nothing much else
    cw, kw = words(base), words(club)
    return bool(kw) and (base == plain(club) or (kw <= cw or cw <= kw) and len(cw) <= len(kw) + 1 and bool(cw & kw))


def kind(title):
    t = plain(title)
    if re.search(r'interview|press|postgame|post-game|speaks|talks|declarati|rueda de prensa|habla|previa|dopo|intervju|infor |efter |after the|media day|on the win|on the loss|🎙', t):
        return 'Interview'
    if re.search(r'highlight|\bpts\b|points|puntos|punti|tasku|dunk|block|career-high|career high|season-high|game-high|assists|rebounds|\d+ ?p\b|mvp|jugador de la jornada', t):
        return 'Highlight'
    return 'Feature'


def secs(iso):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso or '')
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else 0


def main(argv):
    if not os.environ.get('YOUTUBE_API_KEY'):
        print('no YOUTUBE_API_KEY: skipped')
        return 0
    people = [(p['player'], p.get('club') or '', str(p.get('competitions') or '')) for p in U.load('players') if p.get('player') and p.get('status') == 'Confirmed']
    people += [(c['coach'], c.get('club') or '', str(c.get('league') or '')) for c in U.load('coaches') if c.get('coach')]
    try:
        have = json.load(open(PATH, encoding='utf-8'))
    except Exception:
        have = []
    who = {n: (c, l) for n, c, l in people}
    have = [x for x in have if x.get('player') in who and official(x.get('channel', ''), *who[x['player']][:1], re.split(r'[,;/]', who[x['player']][1]))]
    for x in have:
        x['kind'] = kind(x['title'])
    seen = {x['vid'] for x in have}
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(os.environ.get('YT_DAYS', 10)))).strftime('%Y-%m-%dT%H:%M:%SZ')
    found = []
    for name, club, leagues in people:
        try:
            r = get('search', part='snippet', q=f'"{name}"', type='video', order='date', maxResults=15, publishedAfter=since)
        except Exception as e:
            print(f'  {name}: {e.__class__.__name__} {e}'[:160])
            if 'quota' in str(e).lower() or '403' in str(e):
                break
            continue
        for it in r.get('items') or []:
            sn, vid = it.get('snippet') or {}, (it.get('id') or {}).get('videoId')
            title = re.sub(r'&#39;', "'", re.sub(r'&quot;', '"', re.sub(r'&amp;', '&', sn.get('title') or '')))
            if not vid or vid in seen or plain(name) not in plain(title):
                continue
            if not official(sn.get('channelTitle') or '', club, re.split(r'[,;/]', leagues)):
                print(f'  skip (channel): {name} | {sn.get("channelTitle")} | {title[:60]}')
                continue
            seen.add(vid)
            found.append(dict(kind=kind(title), player=name, title=title, src='youtube', vid=vid, thumb=f'https://i.ytimg.com/vi/{vid}/hqdefault.jpg',
                              secs=0, date=str(sn.get('publishedAt') or '')[:10], channel=sn.get('channelTitle') or 'YouTube'))
    # length, and whether YouTube allows the video on other sites (if not, it opens on YouTube)
    for i in range(0, len(found), 50):
        chunk = found[i:i + 50]
        try:
            d = get('videos', part='contentDetails,status', id=','.join(x['vid'] for x in chunk))
            info = {v['id']: v for v in d.get('items') or []}
        except Exception:
            info = {}
        for x in chunk:
            v = info.get(x['vid']) or {}
            x['secs'] = secs((v.get('contentDetails') or {}).get('duration'))
            if (v.get('status') or {}).get('embeddable') is False:
                x.update(src='ytlink', url=f"https://www.youtube.com/watch?v={x['vid']}")
    for x in found:
        print(f"  + {x['player']} | {x['channel']} | {x['kind']} | {x['title'][:70]}")
    keep = sorted(have + found, key=lambda x: x.get('date') or '', reverse=True)[:200]
    json.dump(keep, open(PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'youtube: {len(found)} new, {len(keep)} kept')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
