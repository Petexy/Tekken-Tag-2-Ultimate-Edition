Stand-ins for the launcher's programs in its tests (never the real ones: the real importer can start Tekken
hidden through Steam, the real builder takes 16 GB and an hour):

- importer/launcher.py answers `status`, `owned` and `main` from a case of launcher/model/tests/golden
  ($TTT2_STUB_CASE, its "status", "owned" and "main" objects as the real script prints them);
- importer/import_character.py prints the progress lines of adding or removing characters ($TTT2_STUB_STEP_SECONDS
  apart, default 0.05);
- kit/bin/ttt2-build prints the builder's steps (@step / @progress) for `install GAME FOLDER` and `update FOLDER`,
  $TTT2_STUB_STEP_SECONDS apart (default 0.05), and makes an install the launcher finds: the folder's marker, its
  build record, the user's install record and a game program (a script writing $TTT2_STUB_MARKER when started);
  $TTT2_STUB_FAIL=<step> stops it there with an error, signal:<step> kills it there (SIGKILL: code 137);
  $TTT2_STUB_PIDFILE gets its process id;
- kit/VERSION is the kit version the stub builder records.
