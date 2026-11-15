# LORPcade

A browser arcade on GitHub Pages. Each game is a folder of finished files (`index.html`, `.js`, `.wasm`, ...)
committed to this repo. On every push to `main`, a workflow generates the LORPcade home screen, finds the
games on its own, and deploys everything. Nothing is compiled in CI.

```
endless_sortie/        ->  https://<user>.github.io/<repo>/endless_sortie/
    index.html
    endless_sortie.js
    endless_sortie_bg.wasm
    game.json          (optional)
    cover.jpg          (optional; cabinet screen image, cover.webp works too)
your_next_game/        ->  https://<user>.github.io/<repo>/your_next_game/
tools/                 home screen generator + template + fonts + music tooling
    music/main_menu.mid         source MIDI for the home screen music
    midi_to_opus.py             MIDI -> Opus renderer (fluidsynth + ffmpeg)
    site/music/main_menu.opus   the rendered track that gets published
.github/workflows/pages.yml
```

Game folders can sit at the top level of the repo (as above) or inside a `games/` folder. Either works.

## One-time setup

1. Push this repo to GitHub (default branch `main`).
2. **Settings > Pages > Build and deployment > Source: GitHub Actions.**
3. Push a commit.

## Adding a game

Copy the game's finished files into a new folder. Any folder with an `index.html` is a game, and the folder
name is its URL (letters, digits, `_` and `-` only). Use **relative** URLs inside the game (`./game.js`,
not `/game.js`), since it is served from a subfolder. Wasm needs a real http(s) server, which Pages is.

### `game.json` (optional)

Without one, the game still appears, with a title made from the folder name and an automatic neon colour.

```json
{
  "title": "Endless Sortie",
  "tagline": "Arcade combat flight",
  "description": "One or two sentences about the game.",
  "genre": "Flight combat",
  "players": "1 player",
  "controls": "Mouse + keyboard",
  "accent": "#2de2ff",
  "requires": ["webgpu"],
  "order": 10,
  "hidden": false
}
```

| Field | Effect |
|---|---|
| `title`, `tagline`, `description` | Marquee text and the blurb on the cabinet. |
| `genre`, `players`, `controls` | Small tags under the blurb. |
| `accent` | Neon colour for the cabinet (a bright hex works best). |
| `requires` | `["webgpu"]` shows a warning on the cabinet in browsers without WebGPU. |
| `order` | Lower comes first (default 100). Ties sort by title. |
| `hidden` | `true` still publishes the game at its URL but leaves it off the home screen. |
| `highscore` | Where the game keeps its best score in `localStorage`, so the cabinet can show it. A key name (`"endless_sortie_best"`) or `{ "key": "...", "field": "stats.best", "label": "Best time", "digits": 0 }`. See *High scores* below. |
| `thumbnail` | Image path inside the game folder. Without it, a `cover.jpg` / `.webp` (also `.jpeg`, `.png`, `.gif`) in the folder is used, then the older `thumb.*` names, and without any of those the cabinet gets a generated screen. |

## High scores

Every game is served from the same origin as the home screen, so they all share one `localStorage`, and the
home screen can show a game's best score on its cabinet. The line beside the red button reads `HI 012300`. It reads
`HI 000000` until a score exists and updates by itself, including when the player comes back with the Back button
or a score is saved in another tab.
Two ways to hook a game up:

**1. The game already saves a score.** Name its key in `game.json`. Open the game, play once, then look in
DevTools > Application > Local Storage to find the key. No change to the game is needed.

```json
{ "highscore": "endless_sortie_best" }
```

A value can be a number (`12300`), text (`"2:31.4"`), or JSON. For JSON, say where the score is with `field`
(`"stats.best"`); without it the page looks for `score`, `hiscore`, `highScore`, `high_score` or `best`.
`label` replaces the `HI` caption and `digits` sets the zero padding (default 6; `0` turns padding off).

**2. A new or changed game.** Save the score under `lorpcade:hiscore:<folder-name>`. No `game.json` entry is
needed:

```js
const KEY = "lorpcade:hiscore:endless_sortie";
const best = Number(localStorage.getItem(KEY)) || 0;
if (score > best) localStorage.setItem(KEY, String(score));
```

Things to know: scores live in each player's own browser, so this is a personal best on that device, not a shared
leaderboard (that would need a server). On a `<user>.github.io` project site every repo of yours shares the same
`localStorage`, which is why the convention key is prefixed `lorpcade:`; avoid generic names like `score` in
`game.json`. Clearing site data or private browsing loses the scores.

## Home screen music

The **Sound** switch in the top bar turns on the chiptune bleeps and, if the site has it, loops
`tools/site/music/main_menu.opus` as menu music. It stays off until someone turns it on, so nothing is
downloaded (or played) before then. The choice is remembered per browser, the music fades in and out, and it
pauses while the tab is hidden. Browsers that can't decode Opus (older Safari) just keep the bleeps.

To change the track, edit `tools/music/main_menu.mid` and render it again:

```sh
python3 tools/midi_to_opus.py tools/music/main_menu.mid \
    --soundfont path/to/your.sf2 \
    -o tools/site/music/main_menu.opus
```

It needs `fluidsynth` and `ffmpeg` (with libopus) on your PATH, and writes mono 128 kbps Opus at 48 kHz,
loudness-normalised for menu use. `--stereo`, `--bitrate`, `--gain` and `--no-normalize` change that. Leave out
`--soundfont` and it uses `$SOUNDFONT`, the first `.sf2` in `tools/soundfonts/`, or a system soundfont, in that
order. Soundfonts are big, so `*.sf2` is git-ignored; commit only the rendered `.opus`. Delete the `.opus` and
the site simply builds without music.

**Seamless loop.** The script reads the MIDI's `loopEnd` marker, trims the audio to exactly that point and folds
the reverb tail that rings on past it back onto the start, so the file loops with no click or cut-off tail.
Loudness is normalised with a single constant gain, so fades keep their shape. The MIDI's outro fades every
instrument down to the level the intro starts at (and ends on the same chord the intro opens with), which makes
the loop point a gentle dip rather than a jump. If you write a new track, keep that in mind: end where you begin,
at the same volume, and put a `loopEnd` marker at the last bar line (`--no-loop` skips all this).

The committed track was rendered with TimGM6mb (GPL-2.0), a small General MIDI soundfont. A bigger one such as
GeneralUser GS or FluidR3 will sound fuller.

## Preview locally

```sh
python3 tools/build_site.py                    # writes _site/
python3 -m http.server 8080 --directory _site
```
