# Intended differences from the old launchers

What `launcher::model` shows differently from the old GTK app on purpose.
`model_test` applies I1-I9 to a GTK golden before comparing it (model_test.cpp,
`intended()`) and accepts W0-W8 between the Tk goldens' texts and the model's
Windows views (`kTkDifferences`); anything else that differs fails.

**The name**: the old launchers called themselves Ultimate Launcher. The
goldens (their texts and the release's file names) were changed to Golden Fist
Launcher with the rename of 2026-11-25, and "from an older Ultimate Launcher"
to "from an older version of the launcher": made again from the old launchers,
they differ in just that.

## Linux (compared with the GTK goldens)

- **I1 Settings is always reachable**. The old app had the
  settings button only once the game was installed; the model puts it beside
  Install and Resume too, because Settings now also has the launcher's own
  section.
- **I2 The launcher's own settings**: a section "Golden Fist
  Launcher" after Keyboard with Language (System by default: the system's when
  the launcher has it, else English), Sounds (on by default), Reduce motion and
  Text size (100 %, 125 %, 150 %).
- **I3 Play reads display.ini when it is pressed.** The old app used what
  Settings had last read, so "Prepare shaders before playing" set by hand (or
  before Settings was opened since the launcher started) was missed. The model
  reads the file at Play: the play-shaders case prepares the shaders first,
  where the old app started the game at once.
- **I4 A cancelled removal says calmly what is left**: "Removing cancelled" /
  "The characters removed before stay removed, the others are kept." instead
  of the signal ("It was stopped: Terminated (code 143, see Details)").
- **I5 New ids** (everything that can be activated has one): the header's
  `refresh`, the task panel's `details`, and the uninstall dialog's
  `uninstall-saves`, `uninstall-characters`, `uninstall-cancel` and
  `uninstall-confirm`. The old app's elements had no id there; the comparison
  ignores these ids where the golden has none.

- **I6 "Prepare shaders before playing" is on by default**: where the case's
  display.ini does not say, the golden's switch is on.
- **I7 Home's UPDATE** (players found the separate updates confusing): when
  anything can be brought up to date (a newer launcher that updates itself,
  the game program, characters made by an older importer), one Update
  (`update-everything`, the suggested item) does all of it in order: the
  launcher, then the game program, then the characters. Play stays as an
  ordinary item (none while the game is older than this launcher can run),
  and the game program's own Update is not offered beside it. The launcher's
  notice says "Update on Home gets it first, then brings the game program and
  the fighters up to date." in place of "Update replaces this AppImage with it
  and opens it." Its Update (`notice-update`) still updates only the launcher;
  Home draws it no button while UPDATE includes it. The comparison takes the
  model's UPDATE element as it is (units.cpp `update_all` checks its parts).
- **I8 Add All Owned for every game** (one button that adds them all): Fighters
  has `add-all-owned:all`, which adds every character that can be added now
  from the games that can be used: each game's own and the DLC characters the
  Steam account owns, in one import. The old apps had an Add All per game and
  one Add All Owned for Tekken 7's DLC only. The comparison takes the model's
  element as it is (units.cpp `add_all_everything` checks what it adds).

- **I9 A Game section in Settings** (players asked to be called by their own
  name, and for the game's other languages): first, before the display
  section (which is now called Display, as its tab), with Player name
  (`player-name`, an entry: the name the game shows instead of Player, kept in
  game.ini beside display.ini; empty, the game's own), Language (`language`,
  a list of the game's languages by their English names, kept in game.ini
  too) and Input delay, moved there from the display section (the same
  switch and words, still in display.ini). display.ini's notes are said there
  too. No case has a game.ini, so the entry is empty and the language
  English.

Not seen in the goldens but also changed on purpose: every item that cannot
be used now keeps a reason (`describe.why`) instead of only being
greyed out, and nothing is said only in a tooltip (the blue side shows the
focused item's `describe` block).

## Windows (compared with the Tk goldens' texts)

The rules in `kTkDifferences` (model_test.cpp) name these:

- **W0 Tk's layout, not its words**: the "Game" title above the game card and
  the shoulder buttons' glyphs (L, R, ZL, ZR) beside their keycaps.
- **I2** as above: the launcher's own settings.
- **W1 Display defaults are the game's**: no display.ini means windowed, Auto,
  120 fps on (the runtime's `display::Settings`). Tk assumed fullscreen.
- **W2 Saving errors use Linux's words**: "The display settings cannot be
  saved: <why>" and "The keys cannot be saved: <why>", where Tk said "Cannot
  save: <why>" and "Cannot save the keys: <why>".
- **W3 Task results use Linux's titles** for what both do: "Adding Kazumi
  Mishima failed" where Tk said "Could not add Kazumi Mishima"; Windows-only
  tasks (Set Up Game, Build, Install, Update installed, the launcher's files)
  keep Tk's texts.
- **W4 Folders are chosen, not typed**: each folder row has Browse
  (`folder:<key>`) and shows the folder, no text entry.
- **W5 Every sentence is the model's**: `main.py --query` answers facts
  and codes only; only a worker's `@error` lines carry Python's words.
- **W6 Linux's words where Tk's had drifted, or Tk said nothing**: the
  resolution's Automatic note, the notes on a keyboard.ini or display.ini
  that cannot be used as it is, Steam and DLC ownership ("Your Steam account
  owns 2 of them: only those can be added.", what is not known and why),
  Tekken 7 or 8 not installed, Steam needed by both games, the importer that
  cannot read the game, the outfits warning Tk added.
- **W7 Linux's rules where Tk's had drifted**: a DLC fighter the account does
  not own shows Not owned with no Add (Tk: a greyed Add); the DLC list's count
  and "2 of 3 owned"; the update offer for characters made by an older
  version also while they cannot be updated now (it says why); Tekken 8's
  stand-in moves, packs made by another version (Remove, Remove All).
- **I7** as above: Home's UPDATE, and the notice's sentence ("Update
  replaces this launcher with it and opens it." on Windows).
- **I8** as above: Add All Owned for every game.
- **I9** as above: Settings' Game section with Player name and Language;
  the display section called Display.
- **W8 Linux's sentence with Windows' action**: "Set up the game first: the
  characters are made from it and from your Tekken 7 or Tekken 8." (Tk: "Set
  up the game first: characters are made from it.").

Where the game is built differs, so Windows keeps Tk's words there: an update
of the game "builds it again on this PC from your game", its builds shown as
"0.8.0 (1cab8c6)", and no update offered for a game whose build is not
recorded (Tk's rule: many games from before the record).
