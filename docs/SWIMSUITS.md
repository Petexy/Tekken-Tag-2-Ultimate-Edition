# Recovered Wii U swimwear presets

The Windows launcher has a **Native roster · Swimsuit presets** row and a **Choose swimsuits…** button. Select fighters and use **Restore / update selected**, or **Remove selected swimsuits**. This reads the installed European Wii U game with update v16; no Tekken 7 or Xbox files are needed. Restart the game after changes.

There are 48 presets for 45 fighters. Leo has two swimsuit variants; Ogre has three swimwear accessories. Combot's preset includes his swim cap. Preview images intentionally reuse the default costume images.

Swimsuits appear after existing imported presets. Use Up / Down in the costume chooser to change pages when necessary. Original costumes and all five custom slots are retained.

## Supported fighters

Marshall Law, Lei Wulong, King, Nina Williams, Hwoarang, Ling Xiaoyu, Christie, Jin Kazama, Jaycee, Bryan Fury, Lee Chaolan, Steve Fox, Craig Marduk, Mokujin, Jack-6, Roger Jr., Anna Williams, Wang, Ganryu, Asuka Kazama, Bruce, Baek, Armor King, Lili, Sergei Dragunov, Eddy Gordo, Bob, Zafina, Miguel, Leo, Lars Alexandersson, Alisa Bosconovitch, Ogre, Jun, Panda, Kunimitsu, Slim Bob, Forest Law, Miharu, Combot, Michelle, Alex, Violet, Dr. Bosconovitch, Sebastian.

## Storage and compatibility

- Recovered packs: `<characters>/swimsuits/<fighter>/`.
- Tekken 7 costume imports remain in `<characters>/native/<fighter>/` and can be updated or removed independently.
- Updating or removing a swimsuit pack retains its previous directory under a hidden backup name in `swimsuits/`.
- The Kunimitsu-only prototype is migrated to the new swimsuit collection during this installation.
- The catalog ships identifiers only. Models, textures, skeletons, equipment XML and previews are read from the player's own game.
- Recovered bodies alias each fighter's original asset registries and retain native identity/movesets. Preview IDs use a separate range above existing native-import reservations.

## Command line

```text
python tools/characters/import_swimsuits.py --game PATH_TO_GAME --out PATH_TO_CHARACTER_PACKS
python tools/characters/import_swimsuits.py knm leo --game PATH_TO_GAME --out PATH_TO_CHARACTER_PACKS
python tools/characters/import_swimsuits.py knm --remove --game PATH_TO_GAME --out PATH_TO_CHARACTER_PACKS
```

The runtime must include the swimsuit loader; the launcher checks the installed executable before offering restoration.
