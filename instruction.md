# Cloud saves: Firebase setup

Players get **one sync code** (like `K7QM-2XWB-9TDF`). Type the same code on another device and every LORPcade game
there continues from the same progress: on the home page, in any game's page, and in the Windows build of Lock-On.
There are no accounts and no passwords; the code is the key.

You set this up **once**, for the whole site. It takes about ten minutes and stays on Firebase's free plan.

What you will end up with: a Firestore database, a small set of rules, and the same two values (`projectId`, `apiKey`)
pasted into two config files.

---

## 1. Create the Firebase project

1. Go to <https://console.firebase.google.com> and sign in with a Google account.
2. **Create a project** (or *Add project*). Name it anything (for example `lorpcade`).
3. Turn **Google Analytics off**; nothing here needs it. Create the project.

## 2. Create the Firestore database

1. In the left menu: **Build > Firestore Database > Create database**.
2. Edition: **Standard**. Database ID: leave it as `(default)`.
3. Location: pick the one closest to your players. **You cannot change this later.**
4. Start in **production mode** (the next step sets the real rules). Click **Create**.

## 3. Publish the security rules

1. Still in Firestore, open the **Rules** tab.
2. Delete what is there and paste the whole of [`firestore.rules`](firestore.rules) from this repo.
3. Click **Publish**.

What the rules allow: reading and writing only under `saves/{code}/games/{game}` where `{code}` is a well-formed
12-character code, writes of exactly the shape the games send, and nothing else. Nobody can list the codes in the
database and nothing can be deleted from a browser or the game.

## 4. Get the two values the games need

1. Click the **gear icon > Project settings > General**.
2. Under **Your apps**, click the web icon `</>` to add a web app. Nickname it (`lorpcade`), leave *Firebase Hosting*
   **unticked**, and click **Register app**.
3. You will see a `firebaseConfig` block. Copy two values from it, `apiKey` and `projectId`, and ignore the rest
   (you do not need the SDK or any of the install steps).

```js
const firebaseConfig = {
  apiKey: "AIza....",            // <- copy this
  projectId: "lorpcade-12345",   // <- and this
  ...
};
```

## 5. Paste them into the config files

The same two values go in **two files** (one per repo). The format is identical:

```json
{
  "projectId": "lorpcade-12345",
  "apiKey": "AIza...."
}
```

| File | Used by |
|---|---|
| `lorpcade/tools/site/sync-config.json` (this repo) | the home page and every game on the website |
| `lock_on/sync-config.json` (the Lock-On repo) | the Windows build (it is compiled into the exe) |

Until they hold real values (they ship with `YOUR_...` placeholders) cloud saves are simply **off**: no SYNC button on
the site, no CLOUD SAVE button in the game, and nothing is sent anywhere.

An API key in a web page is not a secret; it only says which project to talk to. The rules in step 3 are what protect
the data.

## 6. Restrict the API key (recommended)

1. Open <https://console.cloud.google.com/apis/credentials> (same Google account, same project).
2. Open **Browser key (auto created by Firebase)**.
3. Under **API restrictions**, choose **Restrict key** and make sure **Cloud Firestore API** is ticked.
4. Leave **Application restrictions** on **None**. The Windows build sends no website referrer, so a
   "websites" restriction would lock it out.

## 7. Publish

- **Website:** commit `tools/site/sync-config.json` and push. The Pages workflow runs `tools/build_site.py`, which copies
  the config and `lorpcade-sync.js` into `arcade-assets/`. The build log says `cloud saves ON` when it sees real values.
- **Lock-On (web):** nothing to change; the game page loads the site's shared script from `../arcade-assets/`.
  Copy its `dist-web` files into the site repo as before.
- **Lock-On (Windows):** rebuild (`cargo build --release`) so the config is compiled in.

## 8. Try it

1. Open the site. A **Sync** button has appeared in the top bar. Click it, then **Create my code**.
2. Open Lock-On, play, and exit. In the Firebase console under **Firestore Database > Data** you will see
   `saves > <your code> > games > lock_on` (the `saves` and code entries are shown in italics; that is normal).
3. On another browser or phone, click **Sync**, enter the code, and **Link**. Lock-On starts from the same progress.
4. In the Windows game: **title screen > CLOUD SAVE** (or press `Y`) > **ENTER CODE**, type the 12 letters and numbers
   (Backspace edits, Enter links).

---

## How it behaves

- **When it syncs.** A game page syncs *before* the game starts, so it opens on the newest save, then sends each save a
  couple of seconds after the game writes it (a burst of saves is one upload) and again when the tab is hidden or
  closed. The **home page** syncs when it opens and whenever you come back to it: it fetches saves from other devices,
  sends anything a game page did not get to send, and refreshes the `HI` scores on the cabinets. The Windows build
  fetches while the window opens, sends after each save, and flushes on exit. Press **SYNC NOW** to force it.
- **Offline is fine.** Nothing waits on the network for more than a few seconds. Changes are kept and sent later.
- **Conflicts.** If two devices both changed the save while apart, the **most recently saved one wins**, and the other
  is kept as a backup (browser: `localStorage` key `lorpcade:backup:<game>`, restore with
  `LorpSync.restoreBackup("<game>")` in the console; Windows: `%APPDATA%\LORPcade\savegame.sync-backup.txt`).
  The one case that asks you is the first time a device that already has progress meets a different save in the
  cloud: you choose which to keep (the other is backed up the same way).
- **A game that is open is never overwritten.** If another device saves while a game page is open, a bar offers
  **RELOAD**; the running game's own state is not replaced behind its back.
- **Only the save is touched.** For a game with folder name `<slug>` the synced data is `localStorage` keys
  `lorpcade:<slug>:<name>` and `lorpcade:hiscore:<slug>`, nothing else.

## Adding syncing to another game

Nothing to build. In the game's `index.html` add `<script src="../arcade-assets/lorpcade-sync.js"></script>`, and have the game
keep its progress under `localStorage` keys named `lorpcade:<folder-name>:<something>` (letters, digits, `_`, `-`; and
`lorpcade:hiscore:<folder-name>` for the number the home cabinet shows). Then call:

```js
await LorpSync.ready;
if (LorpSync.enabled && LorpSync.getCode()) await LorpSync.syncGame(slug, { timeout: 4000 }); // before the game reads its save
if (LorpSync.enabled) LorpSync.watch(slug);                                                    // push later saves
```

`web/index.html` in the Lock-On repo is a complete example (including a button that opens the shared dialog with
`LorpSync.openDialog()` and a "newer save on another device" bar via `watch(slug, { onRemote })`).
Folder names `sync`, `backup` and `hiscore` are reserved.

## Limits and cost

The free (Spark) plan gives 50,000 reads and 20,000 writes a day and 1 GiB of storage; the plan stops serving rather
than billing you if you ever exceed it, and you never added a card. One game launch is one read, a save is one write, and a
home-page visit reads one document per game that has a save. A save document is about 1 KB.

## Security: what this is and is not

- A sync code is 12 characters from a 32-symbol alphabet (60 bits); it cannot be guessed and the database cannot be
  listed, so strangers cannot find saves.
- **Anyone who has your code can read and replace your saves.** That is the whole trade-off of having no login. The game
  tells players to keep it to themselves. A save is also sealed by the game (it detects edits), and a cloud copy that
  fails that check, or the shape check in the browser, is ignored instead of replacing a good save.
- If a code leaks: on one device click **Unlink**, **Create my code**, then enter the new code on your other
  devices, and delete the old `saves/<old code>` entries in the console.
- Abuse is limited by the rules' shape checks and Firebase's quotas, not by authentication. If you ever want more, add
  Firebase App Check for the web (it cannot cover the Windows build) or sign-in.

## Testing without touching production

Run the Firebase emulator (`firebase emulators:start --only firestore`, listening on `127.0.0.1:8080`) and set
`"baseUrl": "http://127.0.0.1:8080"` in `sync-config.json` (browser), or the environment variable
`LORPCADE_FIRESTORE_URL=http://127.0.0.1:8080` (Windows build). `projectId` can be any name there.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| No Sync button on the site | Config still has the `YOUR_...` placeholders, or `arcade-assets/sync-config.json` did not deploy. The build log says `cloud saves OFF`. |
| "Refused by Firestore" / `REFUSED: CHECK THE FIRESTORE RULES` | Step 3 not published, or the key restriction in step 6 blocks Cloud Firestore API. |
| "API key was rejected" | A typo in `apiKey`; copy it again from Project settings. |
| "Firestore database not found" | A typo in `projectId`, or step 2 was skipped. |
| Works in the browser but not on Windows | `lock_on/sync-config.json` still has placeholders, or the exe was not rebuilt, or the key has a *websites* restriction. |
| Code rejected | Codes have 12 letters/numbers and never contain `0`, `O`, `1` or `I`. Dashes and case do not matter. |
| A game page opens on an old save | It could not reach the cloud within 4 seconds, so it started offline. A bar offers RELOAD once the cloud answers. |

## Files, for reference

| What | Where |
|---|---|
| Shared browser code | `tools/site/lorpcade-sync.js` (published as `arcade-assets/lorpcade-sync.js`) |
| Site config | `tools/site/sync-config.json` |
| Security rules | `firestore.rules` |
| Windows client | `lock_on/src/sync/` (`proto.rs` is the shared protocol, `native.rs` the engine) |
| Windows files | `%APPDATA%\LORPcade\sync_code.txt` (the code, shared by all native LORPcade games), `sync_lock_on.txt`, `sync_device.txt` |
| Browser keys | `lorpcade:sync:code`, `lorpcade:sync:s:<game>`, `lorpcade:sync:dev`, `lorpcade:backup:<game>` |
| Cloud layout | `saves/{code}/games/{slug}` = `{ v: 1, at: <ms>, dev: "web-…"/"win-…", data: { save: "…", hiscore: "…" } }` |
