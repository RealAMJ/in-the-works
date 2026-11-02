#!/usr/bin/env python3
"""
Phone alerts for finished games, sent by the GitHub job a few minutes after each game.

For every data/schedule.json row that is final, from the last 2 days, has its post-game work done
("post_done": true, so every Swede's line is in data/boxscores.json) and has no "notified": true,
it sends one message headed "Final:" with a line per Swede, e.g.
  ⭐ Gaddefors (Toruń) W 87-71 vs Zastal Zielona Góra — 18 pts, 8 reb, 0 ast, 36 min
and then sets "notified": true. A row is only marked when the message really went out,
so a failed send is retried on the next run.

Channels (GitHub repository secrets, Settings → Secrets and variables → Actions):
  CALLMEBOT_PHONE + CALLMEBOT_APIKEY   WhatsApp through CallMeBot (free, own number only)
  TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID  Telegram bot message (free, recommended)
  NTFY_TOPIC                           ntfy.sh push (optional extra / fallback)
With no channel set it does nothing.

Run: python3 scripts/notify.py           (--dry-run prints without sending, --test sends a test message)
"""
import datetime as dt
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

SHORT = {
    'Miami Heat': 'Heat', 'Virtus Bologna': 'Virtus', 'Joventut Badalona': 'Joventut', 'UCAM Murcia': 'UCAM',
    'Juventus Utena': 'Utena', 'BC Vienna': 'Vienna', 'Löwen Braunschweig': 'Braunschweig', 'Twarde Pierniki Toruń': 'Toruń',
    'Grupo Ureta Tizona Burgos': 'Burgos', 'Astoria Bydgoszcz': 'Astoria', 'Monbus Obradoiro': 'Obradoiro', 'KK Zabok': 'Zabok',
    'Class Sant Antoni': 'Sant Antoni', 'KR Basket': 'KR', 'CB Zamora': 'Zamora', 'Froya Basket Laksevåg': 'Frøya',
    'Culture City Weimar': 'Weimar', 'Basketball Löwen Erfurt': 'Erfurt',
}


def surname(n):
    return str(n).split()[-1]


def lines_for(g, bx, hl):
    names = [p.strip() for p in str(g.get('players') or '').split(',') if p.strip()]
    lines = []
    star = any(h.get('game_id') == g['game_id'] for h in hl)
    where = 'vs' if g.get('venue') != 'Away' else 'at'
    club = SHORT.get(g['team'], g['team'])
    for n in names:
        b = next((x for x in bx if x.get('game_id') == g['game_id'] and U.norm(x.get('player')) == U.norm(n)), None)
        if b is None:
            return None  # a line is missing: wait
        head = f"{'⭐ ' if star and any(h.get('game_id') == g['game_id'] and U.norm(h.get('player')) == U.norm(n) for h in hl) else ''}{surname(n)} ({club}) {g['score']} {where} {g['opponent']}"
        if b.get('note') == 'DNP':
            lines.append(f'{head} — DNP')
            continue
        extra = [f"{b[k]} {lab}" for k, lab in (('stl', 'stl'), ('blk', 'blk')) if (b.get(k) or 0) >= 3]
        tp = str(b.get('three') or '').split('/')[0]
        if tp.isdigit() and int(tp) >= 4:
            extra.append(f'{tp} threes')
        mins = f", {b['min']} min" if b.get('min') not in ('', None) else ''
        lines.append(f"{head} — {b['pts']} pts, {b['reb']} reb, {b['ast']} ast{''.join(', ' + e for e in extra)}{mins}")
    return lines


def send(text):
    sent = False
    phone, key = os.environ.get('CALLMEBOT_PHONE', '').strip(), os.environ.get('CALLMEBOT_APIKEY', '').strip()
    if phone and key:
        url = 'https://api.callmebot.com/whatsapp.php?' + urllib.parse.urlencode({'phone': phone, 'text': text, 'apikey': key})
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=30) as r:
                body = r.read().decode('utf-8', 'replace')
            ok = r.status == 200 and 'error' not in body.lower()
            print('  whatsapp:', 'sent' if ok else 'failed ' + body[:200].replace('\n', ' '))
            sent |= ok
        except Exception as e:
            print('  whatsapp: failed', e)
    tok, chat = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip(), os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if tok and chat:
        try:
            data = urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode('utf-8')
            with urllib.request.urlopen(urllib.request.Request(f'https://api.telegram.org/bot{tok}/sendMessage', data=data), timeout=30) as r:
                ok = r.status == 200 and '"ok":true' in r.read().decode('utf-8', 'replace')
            print('  telegram:', 'sent' if ok else 'failed')
            sent |= ok
        except Exception as e:
            print('  telegram: failed', str(e).replace(tok, '***'))
    topic = os.environ.get('NTFY_TOPIC', '').strip()
    if topic:
        try:
            req = urllib.request.Request(f'https://ntfy.sh/{topic}', data=text.encode('utf-8'), headers={'Title': 'Final', 'Priority': 'high', 'Tags': 'basketball'})
            with urllib.request.urlopen(req, timeout=30) as r:
                print('  ntfy: sent'); sent |= r.status == 200
        except Exception as e:
            print('  ntfy: failed', e)
    return sent


def main(argv):
    dry = '--dry-run' in argv
    if '--test' in argv:
        ok = send('Final:\nTest from Swedes Abroad: alerts from GitHub are working.')
        print('test', 'sent' if ok else 'NOT sent (no channel worked)')
        return 0 if ok else 1
    if not dry and not ((os.environ.get('CALLMEBOT_PHONE') and os.environ.get('CALLMEBOT_APIKEY')) or os.environ.get('NTFY_TOPIC')
                        or (os.environ.get('TELEGRAM_BOT_TOKEN') and os.environ.get('TELEGRAM_CHAT_ID'))):
        return 0
    sched, bx, hl = U.load('schedule'), U.load('boxscores'), U.load('highlights')
    since = (U.now() - dt.timedelta(days=2)).date().isoformat()
    todo, lines = [], []
    for g in sched:
        if g.get('status') != 'final' or g.get('notified') or not g.get('post_done') or (g.get('date') or '') < since:
            continue
        ls = lines_for(g, bx, hl)
        if ls:
            todo.append(g)
            lines += ls
    if not lines:
        print('notify: nothing new')
        return 0
    text = 'Final:\n' + '\n'.join(lines)
    print(text)
    if dry:
        return 0
    if send(text):
        for g in todo:
            g['notified'] = True
        U.save('schedule', sched)
        U.write_version(True)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
