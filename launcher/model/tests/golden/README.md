# Goldens: what the old launchers showed

Each folder is one case: `case.json` is the fixture (what `launcher.py status`,
`owned` and `main` answered, the install's state, the kit's version, the
files, the test steps), `linux/` is what the old GTK launcher
(`launcher/app`) showed for it and `windows/` what the old Tk window
(`launcher/windows/window.py`) showed for it.

In `linux/`:

- `00-start.json`: once the window had settled after opening;
- `NN-<step>.json`: after each test step (spec linux 6.3's actions:
  `expand-dlc`, `add:kazumi`, `settings`, `bind:face_bottom:46`, ...);
- `NN-<step>-running.json`: while that step's task ran (at half its progress);
- `NN-<step>-stopping.json`: right after Cancel was pressed;
- `tests.txt`: the `@test` lines its test executor printed.

A dump lists, per section (header, notice, game, characters, settings,
task, dialog), every visible element in order: labels with their tone and
tooltip, pills, icons, buttons with their id, label, icon, tooltip, style
class and whether they could be used, check boxes, switches, lists,
expanders, spinners and progress bars. The paths are under `/home/player`
(the case's own folder was put in its place).

In `windows/` (the Tk window has no test steps): `00-start.json`, the main
page once settled with the DLC list open, and `01-settings.json`, the
Settings page.

`launcher_model_test` (ctest label `launcher`) plays every case through
`launcher::model` with the same answers and steps (tests/replay.cpp) and
compares each dump with `flatten()` of the model's view, after applying the
intended differences of [INTENDED.md](INTENDED.md). With Windows' caps it
builds the same two moments and compares their texts (labels, buttons,
pills, check boxes, lists, folder fields; not tooltips, which the new window
does not have, nor the order, which is the new window's) with the Tk dumps:
every text one has and the other has not must be one of INTENDED.md's
(model_test.cpp, `kTkDifferences`). It then plays every case
again with Linux's and with Windows' caps and checks what every view keeps
to (no other OS's items, one id per item, a reason on every disabled item),
activates every id of every first view, and runs the controllers' unit tests.

## How they were made

Not from the specs: from the old app itself (ARCHITECTURE U3). A scratch
copy of the repository, never committed, had a dump hook added to
`launcher/app`'s test executor (where it saves a picture, it also wrote the
widget tree as above), and was run headless (`cage` with the headless wlroots
backend under `dbus-run-session`, its own `HOME` and `XDG_*` folders) with
stand-ins for `launcher.py` and `import_character.py` that answered from each
case's fixture. `launcher_model_golden_convert ROOT RUN_DIR OUT_DIR` (built
with the tests) turned each run's dumps and log into the files here.

To make them again after the old app changes: add the hook to a scratch copy
again, run the cases, and convert each run.

## How the Tk ones were made

The same way: a scratch copy (never committed) of `launcher/windows` with an
entry that replaced the window's UI smoke test by a dump hook walking its
widgets, run by Python 3.13 with Tk under `cage` (its Xwayland, headless),
one fake project folder per case (`launcher.py` answering the fixture,
`local/windows-launcher.json` with the folders model_test also uses, the
installed game's build record), converted by the same tool with `windows`.
