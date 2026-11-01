# Swedes Abroad

Swedish men's basketball players and coaches abroad: games, live scores, box scores and stats.

The site is plain files hosted free on GitHub Pages. A free GitHub Actions job checks the live feeds
every minute during games and saves new scores and box scores into `data/`. Pages that are already open pick up
the new numbers on their own (they check every 20 seconds). None of this uses Claude.

## Set it up (about 10 minutes, all on github.com)

1. **Create the repository.** Go to https://github.com/new, name it `swedes-abroad`, choose **Public**
   (free GitHub Pages needs a public repo), and click *Create repository*.
2. **Upload the files.** On the new repo page click *uploading an existing file*, drag in everything
   from this folder **except the `.github` folder**, and click *Commit changes*.
   (Mac hides folders that start with a dot, so `.github` is added in the next step instead.)
3. **Add the updater.** Click *Add file → Create new file*, type the name
   (already done)
   and click *Commit changes*.
4. **Let the updater save data.** *Settings → Actions → General → Workflow permissions* →
   choose *Read and write permissions* → *Save*.
5. **Turn on the website.** *Settings → Pages → Build and deployment → Source* → choose
   *GitHub Actions*.
6. **Start it.** *Actions* tab → *Live scores and site* → *Run workflow*. When it turns green the
   site is at `https://<your-username>.github.io/swedes-abroad/`.

After that it runs by itself. A run starts every 5 minutes and, while a game is on, checks the feeds
about once a minute and publishes each change, so live scores move roughly every 1 to 2 minutes.
GitHub sometimes starts scheduled runs late, which can leave the odd longer gap.

## Which games update live

| Where the game is | What to do |
|---|---|
| NBA | Nothing. The game id is read from the nba.com box score link (`box_url`). |
| Leagues on FIBA LiveStats (Orlen Basket Liga, ABA, Champions League, FIBA Europe Cup, LKL, BLNO and many more) | Add `"live_feed": "fiba:2949100"` to the game in `data/schedule.json`. The number is the one in the league's live stats link (`fibalivestats.dcd.shared.geniussports.com/u/.../2949100/`). |
| EuroLeague | Add `"live_feed": "euroleague:E2026:45"` (season code and game code from the euroleague.net game link). |

To edit, open `data/schedule.json` on github.com, click the pencil, find the game by its date and
team, add the line after `"game_id": "...",` and commit. Example:

```json
{
 "game_id": "g20261031ast",
 "live_feed": "fiba:2949100",
 "date": "2026-10-31",
 ...
}
```

A game is checked from 20 minutes before tip-off until 4 hours after. When the feed says it has ended,
the result is saved as final and the game is no longer checked.

## Finding live-stats ids automatically

`data/feed_seeds.json` lists one known FIBA LiveStats game id per competition. Games of the same
league get ids close to each other, so `scripts/discover.py` scans around that id and adds
`live_feed` to new games of that league by itself. Add one id for a new league and it is covered.
To fetch a finished game's box score once, add `"live_feed": "fiba:<id>"` and `"backfill": true` to its row.

## What stays manual

The updater handles scores and box scores. New fixtures, season averages, stories on *This week*,
player bios and photos are data files in `data/` that you (or Claude, when you ask) update by editing
the JSON. Each file is one list of rows; keep the same field names as the rows already there.

## Files

| File | What it is |
|---|---|
| `index.html`, `site.css`, `site2.css`, `i18n.js` | The site, including the English/Swedish switch |
| `theme.css` | Colours, fonts and spacing, light and dark mode |
| `dash-shim.js` | Loads `data/*.json` into the page and refreshes it when the data changes |
| `data/*.json` | All data: games, box scores, players, stats, stories, bios… |
| `data/_version.json` | Fingerprints of the data files; the page polls this to know what changed |
| `scripts/update.py` | The live updater (Python 3, no extra packages) |
| `.github/workflows/live.yml` | Runs the updater (about once a minute during games) and publishes the site |

## Try it on your computer

```sh
python3 -m http.server 8000      # then open http://localhost:8000
python3 scripts/update.py --game g20261031ast   # fetch one game's live feed right now
```
