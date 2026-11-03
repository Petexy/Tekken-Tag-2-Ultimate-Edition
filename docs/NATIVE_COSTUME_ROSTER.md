# Native roster costume importer (Windows experiment)

Open **Start Costume Test.cmd**, then **Native roster · Tekken 7 costumes → Choose presets…**.
Pick a fighter, tick presets and choose **Import / update fighter**. The bulk button
imports every supported target. Close the game before changing packs and restart afterward.
Conversion is a long task; completed model conversions are cached for retries.

In **CHANGE COSTUME**, Left/Right selects costumes, Up/Down changes pages, and
confirm/cancel keep their normal buttons. Each page repeats all native outfits
and five custom slots. Page size depends on how many original outfits the fighter has.
Native identities, movesets, voices and roster cells stay in the game.

Jack-7 goes to Jack-6 (`jac`); Julia goes to Jaycee (`jul`); Marshall goes to
Marshall (`law`). Kunimitsu I/II, Slim Bob and Forest Law are not merged.
Tekken 8 and Tekken 6 costume sources are not added by this change.

The catalog contains 321 current T7 preset sets across 34 targets. Deprecated
DefaultCos1P_old/DefaultCos2P_old sets are omitted; named legacy outfits such as
1p_old remain available. Lee's demo_vio and Zafina's swim have no source thumbnail;
their cards explicitly say No source preview. Their model conversion still runs.

| Target | Native code | Presets | Imported per page | Pages |
| --- | --- | ---: | ---: | ---: |
| Paul Phoenix | `pau` | 10 | 6 | 2 |
| Marshall Law | `law` | 9 | 5 | 2 |
| Yoshimitsu | `yos` | 8 | 6 | 2 |
| Ling Xiaoyu | `xia` | 9 | 5 | 2 |
| Asuka Kazama | `ask` | 10 | 5 | 2 |
| Jin Kazama | `jin` | 12 | 6 | 2 |
| Devil Jin | `dvj` | 9 | 6 | 2 |
| Lili | `lil` | 10 | 6 | 2 |
| Bob | `bob` | 9 | 5 | 2 |
| Sergei Dragunov | `dra` | 9 | 6 | 2 |
| Bryan Fury | `bry` | 11 | 5 | 3 |
| Jack-7 → Jack-6 | `jac` | 9 | 6 | 2 |
| Julia → Jaycee | `jul` | 8 | 5 | 2 |
| Kazuya Mishima | `kaz` | 10 | 5 | 2 |
| Heihachi Mishima | `hei` | 10 | 5 | 2 |
| Nina Williams | `nin` | 9 | 6 | 2 |
| Anna Williams | `ann` | 8 | 5 | 2 |
| Lars Alexandersson | `lar` | 10 | 6 | 2 |
| Alisa Bosconovitch | `asa` | 9 | 5 | 2 |
| King | `kin` | 11 | 5 | 3 |
| Armor King | `aki` | 8 | 5 | 2 |
| Eddy Gordo | `edd` | 8 | 5 | 2 |
| Feng Wei | `fen` | 9 | 5 | 2 |
| Ganryu | `gan` | 8 | 6 | 2 |
| Hwoarang | `hwo` | 10 | 5 | 2 |
| Kuma | `kum` | 11 | 7 | 2 |
| Panda | `pan` | 11 | 7 | 2 |
| Lee Chaolan | `lee` | 15 | 6 | 3 |
| Leo | `leo` | 9 | 6 | 2 |
| Lei Wulong | `lei` | 8 | 6 | 2 |
| Craig Marduk | `mar` | 8 | 6 | 2 |
| Miguel | `mig` | 8 | 4 | 2 |
| Steve Fox | `ste` | 9 | 6 | 2 |
| Zafina | `zaf` | 9 | 6 | 2 |

Packs live under the configured character folder's `native/<code>/`. Every update
retains its previous pack as `native/.<code>-backup-<id>/`; removing imports also
retains that backup. The converter caches bodies under `.native-costume-cache/v2/`.
Delete a fighter's cache when deliberately reconverting after model-converter changes.
No source assets, models or textures are committed to Git.

The launcher checks for the matching roster-capable runtime. The earlier Paul-only
build cannot load the other targets. Existing Paul packs remain compatible.
Body registry IDs and texture ranges are separate across all native profiles and
from added-fighter presets. The runtime never expands the native 14-entry buffer.

This is experimental model support. Known shading, hair/head layering, cloth and
character-specific attachment differences still need visual testing. Passing model
read-back and identity checks does not certify every costume's appearance.

Dense native presets use the existing mesh reducer when needed, targeting 36,000
vertices and retaining a hard 42,000-vertex publication limit. Their cloth stays
skinned. Large material sections are split to fit the NUD 16-bit index-count field;
triangle topology and winding are checked before publication.

On this PC, all 34 packs / 321 presets passed model, bone, XML, spring, preview,
texture-namespace and vertex/index-bound validation. In-game checks include
Paul, Marshall Law, Jack-7 on Jack-6, Julia on Jaycee, and Kuma. This does not
mean every outfit has been visually inspected.

The installed configuration also boots with the pre-existing added-character
packs: 34 native packs and 450 total outfit bodies register without errors.
Native archive updates and donor-index reads are batched once across the roster.
With all presets enabled, archive preparation still increases startup time.
The previous runtime is saved beside the game as
`TTT2 Ultimate.before-native-roster.exe`.
