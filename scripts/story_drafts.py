#!/usr/bin/env python3
"""
Drafts for the weekly stories (data/thisweek.json), written from the data so the Monday Claude run only
has to polish them instead of researching from scratch. Output: data/_story_drafts.json (not shown on
the site). Every draft has the same fields as a story (story_id, date, kind, players, game_id, headline,
body, stats, week, headline_sv, body_sv, stats_sv) plus "facts": the numbers it was built from.

Drafts:
  * one per standout game (data/highlights.json) in the week, the biggest one as "Lead story"
  * Swede-vs-Swede games (both Swedes' lines)
  * roundups per area (College, NBA, Spain, Rest of Europe) with every Swede's line
  * "Coming up": the next 7 days' games, Swede-vs-Swede games first

Run: python3 scripts/story_drafts.py                 (only Monday 06:00-06:05 Stockholm; drafts the week just ended)
     python3 scripts/story_drafts.py --force [--week-start 2026-11-01]
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

AREAS = [('College', {'NCAA'}, 'College'), ('NBA', {'NBA'}, 'NBA'),
         ('Spain', {'Liga ACB', 'Primera FEB', 'Segunda FEB', 'Copa España'}, 'Spanien'),
         ('Europe', None, 'Resten av Europa')]
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MAN = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']
WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
WD_SV = ['måndag', 'tisdag', 'onsdag', 'torsdag', 'fredag', 'lördag', 'söndag']


def sur(n):
    return str(n).split()[-1]


def line_en(b):
    if b.get('note') == 'DNP':
        return 'did not play'
    s = f"{b['pts']} pts, {b['reb']} reb, {b['ast']} ast"
    if b.get('min') not in ('', None):
        s += f" in {b['min']} min"
    return s


def line_sv(b):
    if b.get('note') == 'DNP':
        return 'spelade inte'
    s = f"{b['pts']} poäng, {b['reb']} returer, {b['ast']} assist"
    if b.get('min') not in ('', None):
        s += f" på {b['min']} minuter"
    return s


def res_en(g):
    return f"{g['team']} {'won' if g['score'].startswith('W') else 'lost'} {g['score'].split()[-1]} {'at home to' if g.get('venue') != 'Away' else 'at'} {g['opponent']}"


def res_sv(g):
    return f"{g['team']} {'vann' if g['score'].startswith('W') else 'förlorade'} med {g['score'].split()[-1]} {'hemma mot' if g.get('venue') != 'Away' else 'borta mot'} {g['opponent']}"


def when(d, sv=False):
    d = dt.date.fromisoformat(d)
    return f"{WD_SV[d.weekday()]} {d.day} {MAN[d.month - 1]}" if sv else f"{WD[d.weekday()]} {d.day} {MON[d.month - 1]}"


def main(argv):
    now = U.now()
    if '--force' not in argv and not (now.weekday() == 0 and now.hour == 6 and now.minute < 6):
        return 0
    if '--week-start' in argv:
        start = dt.date.fromisoformat(argv[argv.index('--week-start') + 1])
    else:  # the site's week runs Sunday-Saturday: the week that ended last Saturday
        start = now.date() - dt.timedelta(days=(now.weekday() + 1) % 7 + 7) if now.weekday() != 6 else now.date() - dt.timedelta(days=7)
    end = start + dt.timedelta(days=6)
    week = f'{start.isoformat()} – {end.isoformat()}'
    sched, bx, hl, fb = U.load('schedule'), U.load('boxscores'), U.load('highlights'), U.load('fullbox')
    games = {g['game_id']: g for g in sched}
    inweek = [g for g in sched if start.isoformat() <= g.get('date', '') <= end.isoformat() and g.get('status') == 'final' and g.get('score')]
    lines = lambda gid: [b for b in bx if b.get('game_id') == gid]
    drafts = []
    # standout games
    pr = {'Triple-double': 5, 'Double-double': 4, 'Season high': 3, '20+ points': 3, 'Perfect shooting': 2}
    hls = [h for h in hl if start.isoformat() <= str(h.get('date', '')) <= end.isoformat() and h.get('game_id') in games]
    hls.sort(key=lambda h: (-pr.get(h.get('tag'), 1), -next((b['pts'] for b in lines(h['game_id']) if U.norm(b['player']) == U.norm(h['player'])), 0)))
    for i, h in enumerate(hls):
        g = games[h['game_id']]
        b = next((x for x in lines(g['game_id']) if U.norm(x['player']) == U.norm(h['player'])), None)
        if not b:
            continue
        top = sorted([x for x in fb if x.get('game_id') == g['game_id'] and not x.get('swede')], key=lambda x: -(x.get('pts') or 0))[:1]
        extra_en = f" {top[0]['player']} led all other scorers with {top[0]['pts']}." if top else ''
        extra_sv = f" {top[0]['player']} var bäst av övriga med {top[0]['pts']} poäng." if top else ''
        drafts.append(dict(story_id=f"draft-{h['highlight_id']}", date=g['date'], kind='Lead story' if i == 0 else ('Double-double' if h.get('tag') == 'Double-double' else 'Big night'),
                           players=h['player'], game_id=g['game_id'], week=week,
                           headline=h.get('headline', ''), headline_sv=h.get('headline_sv', ''),
                           body=f"{h.get('detail', '')}{extra_en}", body_sv=f"{h.get('detail_sv', '')}{extra_sv}",
                           stats=f"{b['pts']} PTS · {b['reb']} REB · {b['ast']} AST · {b['fg']} FG",
                           stats_sv=f"{b['pts']} P · {b['reb']} RET · {b['ast']} ASS · {b['fg']} FG",
                           facts=dict(game=g, line=b, highlight=h)))
    # Swede vs Swede
    for g in inweek:
        sides = {}
        for x in fb:
            if x.get('game_id') == g['game_id'] and x.get('swede'):
                sides.setdefault(x['team'], []).append(x['player'])
        if len(sides) < 2:
            continue
        ls = lines(g['game_id'])
        parts_en = [f"{b['player']} ({next((t for t, ps in sides.items() if b['player'] in ps), '')}): {line_en(b)}" for b in ls]
        parts_sv = [f"{b['player']} ({next((t for t, ps in sides.items() if b['player'] in ps), '')}): {line_sv(b)}" for b in ls]
        drafts.append(dict(story_id=f"draft-svs-{g['game_id']}", date=g['date'], kind='Swede vs Swede', players=g.get('players', ''), game_id=g['game_id'], week=week,
                           headline=f"Swedish duel: {' vs '.join(sur(n) for ps in sides.values() for n in ps)}",
                           headline_sv=f"Svensk duell: {' mot '.join(sur(n) for ps in sides.values() for n in ps)}",
                           body=f"{res_en(g)} on {when(g['date'])}. " + '. '.join(parts_en) + '.',
                           body_sv=f"{res_sv(g)} {when(g['date'], True)}. " + '. '.join(parts_sv) + '.',
                           stats=' · '.join(f"{sur(b['player'])} {b['pts']} PTS" for b in ls), stats_sv=' · '.join(f"{sur(b['player'])} {b['pts']} P" for b in ls),
                           facts=dict(game=g, lines=ls)))
    # roundups
    used = set()
    for name, comps, name_sv in AREAS:
        gs = [g for g in inweek if (g['competition'] in comps if comps else g['game_id'] not in used)]
        gs = [g for g in gs if g['game_id'] not in used]
        if not gs:
            continue
        used |= {g['game_id'] for g in gs}
        en, sv, who = [], [], []
        for g in sorted(gs, key=lambda x: x['date']):
            for b in lines(g['game_id']):
                who.append(b['player'])
                en.append(f"{b['player']} {line_en(b)} as {res_en(g)} ({when(g['date'])}, {g['competition']}).")
                sv.append(f"{b['player']} {line_sv(b)} när {res_sv(g)} ({when(g['date'], True)}, {g['competition']}).")
        drafts.append(dict(story_id=f"draft-roundup-{name.lower()}", date=max(g['date'] for g in gs), kind='Roundup',
                           players=', '.join(dict.fromkeys(who)), game_id=gs[-1]['game_id'], week=week,
                           headline=f"{name} roundup", headline_sv=f"{name_sv}: veckans sammanfattning",
                           body='\n\n'.join(en), body_sv='\n\n'.join(sv), stats=f"{len(gs)} games", stats_sv=f"{len(gs)} matcher",
                           facts=dict(games=[g['game_id'] for g in gs])))
    # coming up
    nxt = [g for g in sched if g.get('status') == 'upcoming' and now.date().isoformat() <= g.get('date', '') <= (now.date() + dt.timedelta(days=7)).isoformat()]
    club = {p['player']: p.get('club') for p in U.load('players')}
    # a Swedish matchup: Swedes on both teams (teammates on the same club don't count)
    duel = [g for g in nxt if len({club.get(p.strip()) for p in str(g.get('players', '')).split(',') if p.strip()}) > 1
            or 'swedish matchup' in str(g.get('note', '')).lower()]
    pick = duel + [g for g in nxt if g not in duel][:8]
    fmt_en = lambda g: f"{when(g['date'])} {g.get('time', '')}: {g.get('players', '')} - {g['team']} {'vs' if g.get('venue') != 'Away' else 'at'} {g['opponent']} ({g['competition']})"
    fmt_sv = lambda g: f"{when(g['date'], True)} kl. {str(g.get('time', '')).replace(':', '.')}: {g.get('players', '')} - {g['team']} {'mot' if g.get('venue') != 'Away' else 'borta mot'} {g['opponent']} ({g['competition']})"
    if pick:
        drafts.append(dict(story_id='draft-ahead', date=now.date().isoformat(), kind='Coming up', players=', '.join(dict.fromkeys(p.strip() for g in pick for p in str(g.get('players', '')).split(',') if p.strip())),
                           game_id='', week=week, headline='Coming up', headline_sv='På gång',
                           body='\n'.join(fmt_en(g) for g in pick), body_sv='\n'.join(fmt_sv(g) for g in pick),
                           stats=f"{len(duel)} Swedish matchups", stats_sv=f"{len(duel)} svenska möten", facts=dict(games=[g['game_id'] for g in pick])))
    json.dump({'made': now.isoformat(timespec='seconds'), 'week': week, 'drafts': drafts}, open(os.path.join(U.DATA, '_story_drafts.json'), 'w'), ensure_ascii=False, indent=1)
    print(f'story drafts: {len(drafts)} for {week}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
