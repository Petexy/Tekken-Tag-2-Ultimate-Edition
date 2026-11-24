# Intended differences from the old launchers

What `launcher::model` shows differently from the old GTK app on purpose.
`model_test` applies I1-I5 to a golden before comparing it (model_test.cpp,
`intended()`); anything else that differs fails.

## Linux (compared with the GTK goldens)

- **I1 Settings is always reachable** (ARCHITECTURE U17). The old app had the
  settings button only once the game was installed; the model puts it beside
  Install and Resume too, because Settings now also has the launcher's own
  section.
- **I2 The launcher's own settings** (U6, U9, U17): a section "Ultimate
  Launcher" after Keyboard with Sounds (off by default), Reduce motion and
  Text size (100 %, 125 %, 150 %).
- **I3 Play reads display.ini when it is pressed.** The old app used what
  Settings had last read, so "Prepare shaders before playing" set by hand (or
  before Settings was opened since the launcher started) was missed. The model
  reads the file at Play: the play-shaders case prepares the shaders first,
  where the old app started the game at once.
- **I4 A cancelled removal says calmly what is left**: "Removing cancelled" /
  "The characters removed before stay removed, the others are kept." instead
  of the signal ("It was stopped: Terminated (code 143, see Details)").
- **I5 New ids** (U14: everything that can be activated has one): the header's
  `refresh`, the task panel's `details`, and the uninstall dialog's
  `uninstall-saves`, `uninstall-characters`, `uninstall-cancel` and
  `uninstall-confirm`. The old app's elements had no id there; the comparison
  ignores these ids where the golden has none.

Not seen in the goldens but also changed on purpose: every item that cannot
be used now keeps a reason (`describe.why`, U7) instead of only being
greyed out, and nothing is said only in a tooltip (the blue side shows the
focused item's `describe` block).

## Windows (what Tk showed; no Tk goldens)

- **W1 Display defaults are the game's**: no display.ini means windowed, Auto,
  120 fps on (the runtime's `display::Settings`). Tk assumed fullscreen.
- **W2 Saving errors use Linux's words**: "The display settings cannot be
  saved: <why>" and "The keys cannot be saved: <why>", where Tk said "Cannot
  save: <why>" and "Cannot save the keys: <why>".
- **W3 Task results use Linux's titles** for what both do: "Adding Kazumi
  Mishima failed" where Tk said "Could not add Kazumi Mishima"; Windows-only
  tasks (Set Up Game, Build, Install, Update installed, the launcher's files)
  keep Tk's texts.
- **W4 Folders are chosen, not typed** (U11): each folder row has Browse
  (`folder:<key>`), no text entry.
- **W5 Every sentence is the model's** (U2): `main.py --query` answers facts
  and codes only; only a worker's `@error` lines carry Python's words.
