# Goldens: what the old GTK launcher showed

Each folder is one case: `case.json` is the fixture (what `launcher.py status`,
`owned` and `main` answered, the install's state, the kit's version, the
files, the test steps), and `linux/` is what the old GTK launcher
(`launcher/app`) showed for it:

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

`launcher_model_test` (ctest label `launcher`) plays every case through
`launcher::model` with the same answers and steps (tests/replay.cpp) and
compares each dump with `flatten()` of the model's view, after applying the
intended differences of [INTENDED.md](INTENDED.md). It then plays every case
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

## Windows

There are no Tk goldens: the PC they were made on has no Tk (Python's
`tkinter` cannot load `libtk8.6.so`). With Windows' caps the cases are
checked for the rules above, not compared with what `window.py` showed;
where Tk said something else than GTK, the model shows what Linux decides
(INTENDED.md, W1-W5).
