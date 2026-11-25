# Changelog

What changed for players in each release: the game program, the added fighters and Golden Fist Launcher (called Ultimate Launcher up to 0.8.0). Downloads, checksums and install notes are on the [Releases](https://github.com/Petexy/Golden-Fist-Launcher/releases) page.

## [0.8.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.8.0) - 2026-11-24

**CUSTOMIZE for added fighters**: 20 of them can wear Tekken Tag Tournament 2's shop outfits, fitted to their own bodies, with colours, PAINT and five saved slots each. Also **PAINT without a Wii U GamePad**, **added fighters keep their own rank and record**, **much lower memory use**, **Azazel with a crouch and a normal guard**, and the Tekken 8 beta testers' second round of fixes for **Clive** and **Miary Zo**.

### The game

- **PAINT works without a Wii U GamePad.** Paint with the mouse or a touch screen, or move a cursor with a controller's right stick and paint with ZR. Strokes are kept, saved with the slot and shown in fights, and the eraser erases instead of painting black.
- **Added fighters keep their own rank, wins and losses** ([#107](https://github.com/Petexy/Golden-Fist-Launcher/issues/107)). They shared Paul's record and were written over other parts of the profile, so every added fighter was a Beginner again after the main menu. Records lost before this release don't come back.
- **Much lower memory use with many added fighters.** The game read and kept every fighter's files at start: 2.4 GB for 23 fighters, more than 7 GB with outfits. It now reads them when they're needed.
- **Linux: no more stutter on a PC short of free memory.** When Linux took back the memory the graphics driver reads the game from, the game ran at 52-55 frames a second instead of 60. It now keeps that memory in place.
- **No more crash while an Arcade stage loads** with Eliza, Geese, Reina or Noctis in a team.
- **A tag team's win screen ends when an added fighter wins.** It stayed on the bonus panel over an empty stage until Start was pressed.
- **The win shots show the added fighters** instead of an empty floor or only their legs.
- **The random "?" can be reached from the second row again** when the select screen has its extra top row (20 or more added fighters).
- **CUSTOMIZE's colours stay right with many added fighters**, for the game's own fighters too: garments no longer go black or white as you turn the hue, and saved slots show their real colours.
- **CUSTOMIZE's REGISTER TAG and TOUCH SELECT no longer lock up on an added fighter.** They take only the game's own fighters and say so.
- **Grids with the extra top row are drawn right.** CUSTOMIZE's cursor sits on its cell, and the button guide no longer covers the bottom row in CUSTOMIZE, the character information or the ending movies.
- **Azazel's round calls and intro are framed for a giant.** "ROUND 1", "READY" and "FIGHT" show him whole, with no black flash, no jolt into the fight and no camera flying out at the next round; his intro has its whole LED wall behind him.

### The added fighters

- **New: CUSTOMIZE for added fighters.** Every human-sized added fighter (all but Gigas, Fahkumram and Azazel) can wear the game's shop outfits for the upper and lower body, fitted to its own body and skin tone, with colours and PAINT. Women shop from Jun's list and men from Lars's, with those prices, and share what you own. Each fighter has five slots of its own, listed in the costume chooser after its costumes. No hair or head items yet. With nothing equipped, a fighter looks as before.
- **Azazel:**
  - holding down crouches and guards lows, and down + a button are still his attacks;
  - walking or dashing forward he no longer blocks everything (lows included); he guards like any fighter;
  - d/f+3+4 leaves him 15 frames ahead instead of 120, so it no longer loops without end;
  - no more Lars voice or subtitles: his intros roar as in Tekken 8, and his wins and the announcer's name call are silent.
- **Clive Rosfield:**
  - Burning Rain (jump 2,2) and Staff of Judgment (f,F+1+2) bound, with their command list icons;
  - Phoenix 2 hits an opponent getting up;
  - f+2 and SS 2,1's second hit reach as far as in Tekken 8, and f,F+2 hits on Tekken 8's frames;
  - f+3, b+1+2, d/b+1+2,1 and b,b+1+4 hit where Tekken 8's do (b+1+2 missed at 2.8 m yet hit at 3.4 m).
- **Miary Zo:** nine moves are as minus on block as in Tekken 8 (d+1+2 is -17, not -14), and Baobab 1,4's last hit bounds, with its command list icon.
- **Tekken 8 moves that start their animation late play in step with their hits.** They ran 1 to 5 frames behind (Clive's f+2 and f,F+2, and a few small moves of the other Tekken 8 fighters).
- **Katarina's coat:** its sleeves reach her wrists as in Tekken 7, and its sides no longer stand out like wings or tilt into her hip.

### Ultimate Launcher

- **New setting: "Prepare shaders before playing"** (off by default; see [#115](https://github.com/Petexy/Golden-Fist-Launcher/issues/115)). Play first prepares every shader the game has already used on this PC, with a progress bar, so the game doesn't stop for them again, for instance after a graphics driver update. What it has never shown is still made the first time.
- **New setting: "Shaders in the background"** (off by default). Some things shown for the first time may appear a few frames late instead of the game pausing while their shader is made.

## [0.7.1](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.7.1) - 2026-11-21

A hotfix for **Tekken 8's update**: Reina, Azucena, Miary Zo, Victor Chevalier, Clive Rosfield and Azazel can be added again.

### The added fighters

- **Tekken 8 fighters can be added and updated again after Tekken 8's latest update** ([#112](https://github.com/Petexy/Golden-Fist-Launcher/issues/112)). Adding one stopped with "this Tekken 8 build (Steam build 26651490, a game update) is not the one the helper knows". The update moved one function the launcher's Tekken 8 helper uses; the helper now knows the new build and still knows the earlier ones. The fighters themselves are unchanged: the update changed none of their moves, so fighters you already added don't need an update.

### The game

- No changes.

## [0.7.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.7.0) - 2026-11-18

**A new fighter from Tekken 8: Azazel**, at his full giant size, with a fight camera that keeps him in the picture. **Clive Rosfield, Miary Zo and Victor Chevalier play much closer to Tekken 8**: beta testers' bug reports fixed, and all Tekken 8 fighters now take hits with Tekken 8's own reactions. Plus **Leroy's parries**, **Gigas's Claw Hammer** and **Tag Assault no longer tags out the fighter who started it**.

### The game

- **A Tag Assault no longer tags out the fighter who started it** ([#32](https://github.com/Petexy/Golden-Fist-Launcher/issues/32), [#96](https://github.com/Petexy/Golden-Fist-Launcher/issues/96)). When Eliza, Geese, Reina or Noctis started a Tag Assault, their next string (Eliza's 1 or b+4, Geese's 1 or 2, almost any Reina move) could tag them out without a Tag press.
- **The fight camera frames a giant**: it pulls back while Azazel is on screen, for his throws and KOs too.

### The added fighters

- **New: Azazel** (Tekken 8). He is about 4 metres tall, as in Tekken 8, and his body, throws and hit boxes fit that size. His crystal pillars rise and crumble away, his beam, projectiles and tail attacks hit, and his b+1 grabs on hit or counter hit. He has a Practice command list made from his moves, and he bounds where he does in Tekken 6.
- **Tekken 8 fighters take hits as in Tekken 8.** Opponents float, land and guard with Tekken 8's own reactions where TTT2's would differ, and Tekken 8's counter-hit and facing tests work. Tornado hits launch as a plain launch.
- **Clive Rosfield:** 1,2 is natural; 1,f+2 and 2,2,1 are guaranteed on counter hit; f+3 reaches as far as in Tekken 8 (no longer from 3.1 m); qcf+1 hits up close; d+1+2 and ws+2 on hit, b+4 and f,f+2 on counter hit react as in Tekken 8; Phoenix 2,1's second hit connects, also after running 2.
- **Miary Zo:** 3,1,2's last hit can be blocked and hits on counter hit; u/f+4,4 launches; Baobab 4 launches on counter hit; f,f+2,2's second hit comes out after a blocked first; b+1,4, f+1+2,1+2,3+4, FC d/f+4 and Morengy 2 react as in Tekken 8; Tag in a juggle after d+2 or d/f+1,1,2 bounds and brings the partner in.
- **Victor Chevalier:** u/f+4 launches; b+2 and the pistol of d/f+4,2 hit; d/b+4 counter hit leads into its follow-up; 1,2,1, 1+2, d/b+3, ws+1 and Iai 1+2 react as in Tekken 8; Iai 1,2,2 + Tag bounds instead of vanishing.
- **Tekken 8 fighters' power crushes no longer sound armoured.** TTT2 has no armour, so the armour sounds are left out (Clive's b+1+2 and the others).
- **Leroy's b+2 parries highs and mids, and Geese's counters counter** ([#105](https://github.com/Petexy/Golden-Fist-Launcher/issues/105)). Every Tekken 7 parry and counter was lost when a fighter was added. Negan's bat-stance parries get their missing rows too.
- **Gigas's Claw Hammer (his air throw) deals 20 when it ends a juggle** ([#101](https://github.com/Petexy/Golden-Fist-Launcher/issues/101)). TTT2 doesn't reduce throw damage in a combo, so Tekken 7's 60 came on top of a full juggle. A jumping opponent still takes 60.
- **Master Raven's Tag Assault strings** (3+4,4, the meteor and the roll kick) no longer start hidden.

### Ultimate Launcher

- **Play waits for Update when the game is older than the launcher.** After the launcher updated itself, Play stayed on with a game built by an older launcher, which plays newer fighters wrong (missing summons and effects, other hit reactions). The game card now shows Update in Play's place, and adding or updating fighters waits for it too.
- **Windows: Set Up Game no longer stops at "Preparing graphics libraries"** with "error adding trust anchors from file" ([#102](https://github.com/Petexy/Golden-Fist-Launcher/issues/102)). Git settings left by an earlier Git for Windows could name a certificate file that no longer exists; the downloads now use Windows' own certificates.

## [0.6.2](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.6.2) - 2026-11-12

A hotfix for 0.6.1: **Set Up Game works again on Linux, and Tekken 8's fighters can be added again after Tekken 8's update of 12 November.**

- **Linux: Set Up Game and the game's updates stopped at once with code 127** (`libcrypto.so.4: cannot open shared object file`) since 0.6.0, on SteamOS, Ubuntu, Fedora, Debian and most other systems ([#91](https://github.com/Petexy/Golden-Fist-Launcher/issues/91)). The launcher's build tools needed OpenSSL 4, which only a few rolling distributions have yet. They need OpenSSL 3 again, as up to 0.5.1, and every release is now checked to need no library those systems lack.
- **Tekken 8's fighters couldn't be added or updated after Tekken 8's update of 12 November** (Steam build 26155785): "this Tekken 8 build … is not the one the helper knows" ([#93](https://github.com/Petexy/Golden-Fist-Launcher/issues/93)). The launcher knows the new build, and still the one before it. The update also renumbered moves, which broke adding Clive Rosfield and would have put Azucena's, Victor Chevalier's and Miary Zo's bounds on the wrong moves; their moves are now found the same way in every build. Fighters you added before keep working either way.
- **Windows: when adding a fighter failed, a box said only `'import'`** and the launcher's bar stayed at "Starting…". It now says "Could not add …" and why.

The game and the fighters are unchanged since 0.6.0. For everything 0.6.0 brought (Miary Zo, Victor Chevalier and Clive Rosfield, floor breaks and move sounds for all Tekken 8 fighters, Noctis's warps), see [0.6.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.6.0); 0.6.1 made Miary Zo and Clive Rosfield addable with their DLC owned.

## [0.6.1](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.6.1) - 2026-11-12

A hotfix for 0.6.0: **Miary Zo and Clive Rosfield can be added again when you own their DLC.**

- **Miary Zo's and Clive Rosfield's Add stayed greyed out** in 0.6.0, even with their Tekken 8 DLC owned: the launcher asked Steam which DLC you own only through Tekken 7, so their ownership was never known. Both launchers now ask through Tekken 8 too, with Steam running and Tekken 8 installed, and show **Add** for the Tekken 8 DLC fighters you own.
- If Steam can't be asked through one of the games (for example while it is running), the other game's DLC fighters stay addable, and the launcher says why.

The game and the fighters are unchanged since 0.6.0. For everything 0.6.0 brought (Miary Zo, Victor Chevalier and Clive Rosfield, floor breaks and move sounds for all Tekken 8 fighters, Noctis's warps), see [0.6.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.6.0).

## [0.6.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.6.0) - 2026-11-12

**Three new fighters from Tekken 8: Miary Zo, Victor Chevalier and Clive Rosfield**, made from your own Tekken 8 like Reina and Azucena, with their own moves, voices, move sounds, weapons and creatures. **All Tekken 8 fighters break floors, play their move sounds, and their moves are as minus on block as in Tekken 8.** And **Noctis's warps show**: he fades into blue light and back instead of popping from place to place.

### The game

- **Summoned weapons grow in and shrink away as in Tekken 8**, such as Miary Zo's staffs, tail and horn, and Bahamut's wings form and dissolve. Summons are put away when a round starts or their owner is hit or thrown.
- **Weapons a fighter carries stay on between moves**, through hits and throws too, such as Victor's scabbard, knife, karambit and holstered gun.
- **Summoned creatures act where the move set them down** and are drawn steady, even when the opponent holds their fighter back.
- **Motion blur leaves Clive's creatures and summoned blades sharp**, as Tekken 8 draws them.

### The added fighters

- **New: Miary Zo** (Tekken 8 DLC). Her staffs, tail, horn and snakes appear in their moves, glow and hit. Her d+2, d/f+1,1,2, b+1+2, Morengy Miroso 1+2 and ws3 bound.
- **New: Victor Chevalier** (Tekken 8). His katana, knife and karambit hit, and his warp, gun shots, bombs and his sword's flame arc come with him. His Iai Stance 1,2,2, Perfumer 1+2, f+1+2 and u+1+2 bound.
- **New: Clive Rosfield** (Tekken 8 DLC). Torgal, Garuda, Bahamut's wings, the phoenix, Titan, Leviathan and Shiva come out in his moves, with his big slash arcs, and Torgal runs in for his 1+3 throw. His f+3, f,F+2, f+2,2,2 and jump 1 bound.
- **Tekken 8 fighters break the floor** with the throws and moves that do in Tekken 8, such as Reina's 1+3 and SSH.CH.3 and Azucena's LIB.d+3 on an airborne opponent. Floor breaks that need Heat don't.
- **Tekken 8 fighters' move sounds:** swings, hits and shots come from Tekken 8. Before, only their voices played.
- **Tekken 8 fighters' hands move as in Tekken 8.** Before, their fingers kept one fixed shape.
- **Blocked Tekken 8 moves are as minus as in Tekken 8:** Reina's 4 is -8 on block, not -13.
- **Tekken 8 fighters no longer jump-attack out of a walk or run at any moment.** Their walks and runs took inputs meant for other moves.
- **Tekken 8 moves that reach from the ground under the fighter, or with a later hit box, hit where they should**, such as Reina's Sentai 3 and Azucena's d/b+3+4.
- **Reina and Azucena look closer to Tekken 8:** elbows and knees keep their shape when bent, cloth and hair hang and swing better, and their blinks fit their eyelids.
- **Tekken 8 fighters' throw victims no longer spin on the ground as they go down.** They lie and get up as Tekken 8 drops them, instead of turning up to a full circle after about 50 of Reina's and Azucena's throws.
- **Tekken 8 fighters' select cells and faces in fights show head and shoulders**, as big as the other fighters' faces, in the colours of their portraits (they were bluer and pinker).
- **Kunimitsu II's f+1+4, Gigas's Overkill and Josie's f,F+3+4 throws connect.** They grabbed, showed a high and did nothing.
- **Noctis's warps are seen** (Warp-Strike f+2 and the others): he fades out in blue light and back in, a streak of light marks his way, and his weapons glow as he summons and dismisses them.
- **Tekken 7 fighters' effects as player 2 start facing their own way**, not player 1's.

### Ultimate Launcher

- **Windows: Update All updates the DLC fighters too** (#80). It took only the base game's, so DLC fighters had to be updated one by one.

## [0.5.1](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.5.1) - 2026-11-03

**Update and Remove work again after Tekken 7 or Tekken 8 is uninstalled.** On **SteamOS, the launcher fetches what adding fighters needs** itself, with no terminal or container. And many **fixes to the added fighters' moves**, from the beta testers and your reports.

### The game

- **'?' on the select screen can pick the added fighters.**
- **Long sessions no longer get slower.** Textures the game hasn't used for 30 seconds are freed.
- **Added fighters push the opponent with the right body size.** They used sizes that were too big.
- **Weapons hit where the hand is in that frame**, not where it was a frame before.
- **Hit-grabs are scaled in combos.** Noctis's Warp-Strike (f+2), Kunimitsu II's kunai (qcf+1) and Reina's and Azucena's hit-grabs did their full damage at the end of a juggle.
- **Tag Assault into Geese's qcf+2 at the wall:** the partner who stays in can fight at once. Before, they crouch-walked backwards until the super ended.

### The added fighters

- **Hits land where they should.** About 500 moves of the Tekken 7 fighters had their hit at the wrong place, so some kicks and Negan's knife went through the opponent. Reina's and Azucena's jabs, kicks and throws are fixed too.
- **Counter-hit and special reactions stay Tekken 7's own:** Katarina's and Lidia's trips, Master Raven's and Shaheen's counter hits, Leroy's d/f+2,1+2 spin. Their follow-ups work again.
- **Follow-ups that need a hit come out on hit only.** The ones Tekken 7 and 8 also allow on block come out on block too, such as Kunimitsu II's Musasabi jump-off and Reina's Sentai 1+2.
- **Tag Assault:** an added fighter comes in with their own d/f+1. Akuma's d/f+1,2 can start one.
- **Leroy:** d/f+2,1+2 combos into qcf+2, d/b+2,1+2 hits a grounded opponent, Sugar (2+3) hits, and the cane works.
- **Claudio:** Starburst is given and used (d+1,2 after b+2), and d+1,2 hits twice.
- **Negan:** the last hits of 1,2, 4,2 and 1,4,2 connect, the qcf+1 knife is in his left hand, and 4 from his Intimidation stance hits in a combo.
- **Noctis:** u/f+3, b+2,1+2, 2,2 after d/f+2 and WS1,2 at tip range hit. Blocked f+2, 2,2,b+2 and d/f+1,2 end as they should, and the sparks of 2,2,2,2 come from his sword.
- **Kunimitsu II:** her kunai sits in her closed right fist and her sheath at her hips. The short sword shows only in her sword moves. Blocked qcf+1 recovers, and Musasabi 4 jumps off on hit and block.
- **Weapon hit sounds** for Noctis's sword, Kunimitsu II's sword and kunai, and Negan's bat.
- **Akuma's Demon Flip (Hyakkishu) no longer starts under the floor** (#66). He no longer jumps a metre into each follow-up, and Hyakkigozan's landing slide no longer dips into the floor.
- **Reina** (#65): Hell Axle (Heaven's Wrath 3,4) gives its second kick on hit and on block, and WS1 goes into Sentai.
- **Azucena** (#65): f+3 hits, and back-turned 2,2 (or 2, 1+2) grabs. 2,1,2, d/f+4,1, d/f+1,4,1 and f+4,4 connect in the open, and her launches and hit reactions are Tekken 8's.
- **Gigas:** counter-hit f+1+2 at the wall ends in his own head smash. **Kazumi:** f,F+2 shows her tiger. **Chloe:** f+4,4's second hit connects.

### Ultimate Launcher

- **Update and Remove no longer need the other game** (#62). After Tekken 8 was uninstalled, Update and every Remove were greyed out, for the Tekken 7 fighters too. Each fighter now keeps its own copy of the pictures and name call that the select screen is made from. Fighters added with 0.5.0 reuse what your characters folder already has, so they don't need to be added again. Updating a fighter still needs its own game.
- **Linux: a Download button for numpy and Pillow** (#67). On SteamOS, Python has neither, and they can't be installed the usual way. The Missing row now offers Download: about 24 MB into the launcher's own folder, each file checked. No terminal, pip or container needed.
- **Linux: adding fighters needs no C compiler.** The launcher brings the importer's compiled parts with it.
- **Linux: when Tekken 7 or 8 can't start in the background**, for example inside a distrobox container, the launcher says why at once instead of after 90 seconds (#67).

## [0.5.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.5.0) - 2026-11-01

A new Offline mode, **Solo Ghost Battle**. **CPU-controlled added fighters now fight back** instead of standing and crouching. **Noctis is much lighter on the GPU**, and the game uses **less CPU on Linux and Windows**. On NVIDIA and Intel GPUs, **Armor King's green mist** shows again.

### The game

- **Solo Ghost Battle**, a new Offline mode right below Ghost Battle. You pick one fighter, and every ghost fights you one on one. Wins, ranks and rewards are shared with Ghost Battle.
- **CPU-controlled added fighters attack** (#26). As CPU opponents they mostly walked, stood and crouched. Now they fight, though for now they play simpler than the original fighters.
- **Armor King's green mist** (f, N, d, d/f+1+2) shows on NVIDIA and Intel GPUs (#59). So do the glow of his 1+2+3+4 and the background blur in fights, as they always did on AMD and the Steam Deck.
- **Ghost Battle:** an added fighter's ghost that fights alone no longer brings ZAKO B along as a tag partner.
- **Less CPU use on Linux**, most of all on the Steam Deck and SteamOS (#15, #56). The game now asks for the larger memory pages that the graphics driver handles faster. On a system set up as SteamOS is, the graphics thread's CPU use in a fight dropped by about two thirds.
- **Less CPU use on Windows** (#45, #48). Short waits no longer keep a processor core busy. In our tests under Wine, the game needed about half the CPU it did.
- **Less GPU time per frame** on graphics cards with their own memory: about 15% in a fight on a Radeon RX 9060 XT. Fighters' animated models now stay in video memory.
- **The game's log says more:** its graphics setup and, every 10 seconds, its CPU use. Please attach it to bug reports.

### The added fighters

- **Noctis no longer slows the game down** (#55). His model had 89,000 vertices, all of his summoned weapons included. Now it has 48,600, and a fight with him takes about a third less GPU time. Smaller GPUs played in slow motion with him on screen.
- **Akuma's, Eliza's and Geese's gauges:**
  - Each gauge sits under its own fighter's life bar, as in Tekken 7, and no longer covers the texts at the bottom of the screen.
  - The gauge carries over between rounds and empties only when a new match starts. Before, every KO emptied it.
  - Akuma's and Eliza's gauges play Tekken 7's sound when they fill up.
  - Akuma's air fireball points along its path from its first frame.
- **A Tekken 7 file that Tekken 7 itself refuses to hand over no longer stops an import** (#51). The fighter is added unless it needs that very file, and the error then names it. With Outfits ticked, an outfit that needs such a file is left out with a warning.

### Ultimate Launcher

- **Linux: when the game stops with an error,** the launcher shows the last lines of its output and where the whole log is (`~/.cache/ttt2/game.log`).
- **Debian and Ubuntu: the launcher finds shaderc** (`libshaderc1`). It said shaderc was missing although it was installed (#54).
- **Windows: Set Up Game works on exFAT and FAT32 drives**, on drives from another PC, and after a setup that stopped half-way (#60). It failed at "Preparing graphics libraries" every time. Build and Rebuild now say to use Set Up Game when those libraries are missing.
- **Windows: the page has a scroll bar you can drag** (#46). Page Up, Page Down, Home, End and the arrow keys scroll it, and Tab brings the focused control into view. Ticking Outfits or coming back to the window no longer jumps to the top.
- **Windows: updating the launcher no longer starts the downloaded file to check its version.** That start is where virus scanners can hold a new program. The window also stays responsive while the new version opens.

## [0.4.2](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.4.2) - 2026-10-30

A hotfix for 0.4.1: **fighters with their Outfits box ticked can be added and updated again.**

- **Adding or updating a fighter with Outfits ticked failed** in 0.4.1 with "The importer failed: AttributeError: 'bool' object has no attribute 'build'". Fighters with Outfits unticked weren't affected, and a failed update left the fighter's pack as it was: update them again now.

The game itself is unchanged since 0.4.1. For everything 0.4.1 brought (Tekken 7 power gauges for Akuma, Eliza and Geese, optional outfits, the Windows importer fix), see [0.4.1](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.4.1).

## [0.4.1](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.4.1) - 2026-10-30

**Akuma, Eliza and Geese now have Tekken 7's power gauge**: their EX moves, supers and cancels cost gauge again, and each one has their own bar from Tekken 7. **Outfits are now your choice**: without them, adding and updating fighters is much faster. On Windows, adding and updating fighters no longer asks you to set up the game again.

### The added fighters

- **Tekken 7 power gauges for Akuma, Eliza and Geese.** Their EX moves, supers and cancels used to be free. Now they cost gauge as in Tekken 7, and the gauge fills as in Tekken 7 when they take or deal damage. Each bar comes from Tekken 7's own HUD.
  - **Akuma:** EX moves, Messatsu Gou Hadou and Focus cancels cost gauge. The gauge carries over between rounds. Spending it makes him flash yellow.
  - **Eliza:** her EX moves, her super and the cancels into them cost gauge, and she has her bat-wing bar. Sleeping and her long crouch build gauge, as in Tekken 7.
  - **Geese:** three stocks and **MAX mode** (1+2+3). His EX moves need MAX mode, the MAX cancel dash costs a stock, and his supers spend two stocks. He glows light blue while MAX mode runs.
- **Supers stop time** as in Tekken 7: the opponent freezes while the super starts, and a close-up camera shows the attacker. Geese's 1,2,1,2 into Double Reppuken now combos.
- **Projectiles hit once per projectile.** Raging Storm no longer deals 230 damage at once, and Double Reppuken hits five times, not once.
- **Tekken 7 sounds** for a super's or EX move's start, Akuma's fireball, Geese's Reppuken and their projectiles' hits.
- **Akuma's air fireball** flies along its angle and stops at the floor. He stays in the air until he has thrown it.
- **Eliza's air specials:** the EX version no longer hides the plain one on the same input.
- **In Practice,** the gauges sit above the frame data panels.

### Ultimate Launcher

- **Outfits are optional.** Each fighter has an **Outfits** box, and **Import outfits for every character** ticks them all. Outfits are the extra costumes in the costume chooser, and they make adding or updating a fighter take much longer, so new fighters start without them. Fighters whose outfits you already have keep them when updated: their box starts ticked. To add or remove a fighter's outfits later, change their box and click **Update**.
- **Windows: adding fighters no longer asks you to set up the game again.** If the launcher's folder lacks numpy, Pillow or the C compiler, Add, Update and Remove download them first. This happens when Set Up Game ran from another copy, such as the project ZIP.

## [0.4.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.4.0) - 2026-10-29

Ultimate Launcher now adds experimental support for **Windows**. Practice mode gets **frame data, hitboxes and slow motion**, **local multiplayer** works with every keyboard and controller, **Azucena** joins from Tekken 8, and **bounds follow the Tekken 7 Bound Mod**.

### Windows

- **Ultimate Launcher for Windows.** `Ultimate_Launcher-x86_64.exe` sets up the game on Windows 10 and 11: choose your `.wua` and a folder, and it downloads its own tools, builds the game on your PC and installs it. You don't need to install Python, Git or anything else. It has the Linux launcher's page: **Play**, **Settings** (display, input delay, keyboard keys), and fighters to add, update or remove. It updates itself when a new release is out. The Windows version of the game is DeReggie's work (#23, #28).

### The game

- **Practice: ULTIMATE SETTINGS.** In the pause menu, TOUCH SELECT is now ULTIMATE SETTINGS, with:
  - **Frame data** for each player, as in Tekken 8: damage, startup, frame advantage and more.
  - **Advantage colours:** the fighter ahead in frames is blue, the one behind is red.
  - **3D hitboxes.**
  - **A view from above** in a small window.
  - **Slow motion:** 1/2 or 1/4 speed.
- **Practice: input history and reset hint.** The input history looks like Tekken 8's and is on from the start. A hint shows the position reset (Select + 3).
- **Local multiplayer.** In VS Battle, Team Battle and Pair Play, each keyboard or controller that presses **+** (Start) on the player entry screen joins as a player. The entry screen pictures the device each player holds. In the other menus, every device still controls the game.
- **The 19th added fighter no longer freezes a match** right after "Fight".
- **Room for more than 19 added fighters.** From the 20th on, the select screen gets a new top row.
- **Leverless controllers** can move in fights with the D-pad as the left stick (DeReggie).
- **Added fighters' Tag Assaults and combos** (DeReggie): Eliza's Moon Glide strings work during a Tag Assault, Noctis's airborne strings and hit-grab follow-ups work, and counter-hit crumples, running exits and the partner's movement are fixed.

### The added fighters

- **Bounds as in the Tekken 7 Bound Mod.** Screws, Tekken 8's tornados and Tekken 7's slams no longer become bounds. Each fighter bounds only with its own list of moves, once per juggle: for Tekken 7's fighters, the moves the Tekken 7 Bound Mod makes bounds. A screw no longer uses up the juggle's bound. The [README](https://github.com/Petexy/Golden-Fist-Launcher#bound-moves) lists every fighter's bound moves.
- **Azucena from Tekken 8.** She has her own moves, voice, pictures, command list and bounds. Libertador evades highs and lows on its own, as in Tekken 8. Needs Tekken 8.
- **Tekken 8 clothes swing:** Reina's jacket, Azucena's sleeves.
- **Tekken 7 fighters' eyelids** close as in Tekken 7, instead of hanging down the cheeks.
- **Move fixes by DeReggie** for Akuma, Geese, Eliza, Fahkumram, Noctis, Negan, Katarina, Kunimitsu II and Reina: special and super cancels, strings and counter-hit reactions. Noctis's WS 2,2 screws without using up the bound, and Geese's f,d,d/f+2 bounds on its second hit. The full list is in #23.

### Ultimate Launcher

- **Windows**, as above.
- **Newer changes on main.** Both launchers tell you when `main` has fixes newer than your release, and which fighters they update. You see them before a release brings them.
- **Azucena** is in the fighters list.

#### Kunimitsu II in detail (DeReggie) — back-turned attacks and combo collision

- Restore Kunimitsu's own BT 1 animation for both stance-side variants, retaining its frame-15 hit timing and BT 1,2 / BT 1,3 follow-ups.
- Redirect retained native BT 1 input routes to those restored attacks. Keep BT 2 and 1+2 input routes unchanged.
- Extend BT 1's collision coverage downward with an invisible point approximately 350 mm below her hand at impact, while retaining the existing arm collision points.
- Extend the kick in BT 1,3 approximately 100 mm forward at its first active frame (approximately 93 mm at the following frame).
- Apply the collision points to the default costume and all nine installed alternate outfits. Preserve existing bones and visible model geometry, textures, animations, hit timing, damage and Bound rules.
- Install the collision adjustment through a targeted update: four moveset bytes plus collision skeleton/spring metadata and the pack manifest. Back up affected files first; do not run the full importer, rebuild models or regenerate shared assets.
- Preserve the adjustments in the character definition for future imports. Collision points use the shared converter on Windows and Linux; Linux gameplay has not been retested for this adjustment.

Validation (2026-10-26): BT 1's restored animation was confirmed working in-game by the user. The collision update passed 24 relevant unit tests, geometry checks across all ten outfits, and an installation/idempotence check. In-game verification of the adjusted combo remains pending: d/f+2 -> b+4~b -> BT 1,3 -> SET.

Outstanding: Kunimitsu's open-hand weapon grip is a separate issue and is not fixed by these changes.

## [0.3.1](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.3.1) - 2026-10-26

Adding **Tekken 7 fighters works with Proton-GE**, and **Reina's d/f+1,2 is a bound**.

### The added fighters

- **Tekken 7 fighters with Proton-GE.** If Tekken 7 runs with Proton-GE (or another Wine Staging build), adding its fighters stopped with "this Tekken 7 build is not the one the helper knows", even with the right Tekken 7 version. That's because Proton-GE loads the game at a different place in memory. The launcher now finds the game wherever Proton loads it. (#18)
- **Reina's d/f+1,2 is a bound.** Its second hit slams an airborne opponent into the floor, once per juggle, as her d+2, f+4 and f,f+4 do. The command list shows the bound icon on it.

### The game

- **No changes.** The game program is the same as in 0.3.0. The game card still offers **Update**, because the launcher's version changed, but you don't need it for this release.

### Ultimate Launcher

- No changes besides the fighters above.

## [0.3.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.3.0) - 2026-10-26

**Tekken 8's Reina** joins from your own Tekken 8, every added fighter gets **tag combos**, and the game drops the Wii U version's **forced input delay**.

### The game

- **No forced input delay.** The Wii U game waited two frames (33 ms) after a button press before acting on it, in every mode. That wait is gone. The **Input delay** switch in the launcher's Settings brings it back, and Practice's own Input Delay setting works either way. (#17)
- **Smoother on slower processors.** The game turns its graphics commands into Vulkan with much less work, and while that falls behind, the extra frames for 120 fps are left out instead of slowing the game down. There are also far fewer shaders to compile the first time you play, so fewer stutters. (#15)
- **The position reset in Practice is now 3 and − (Select).** + (Start) opens the pause menu at once again.
- **New lettering on the title screen.** "ULTIMATE EDITION" under the logo now follows Excentrian's design. (#9)

### The added fighters

- **Tekken 8's Reina.** She is added from your own Tekken 8, with no Tekken 7 needed. She comes with her moveset and command list, her voice (each move's own line), her electrics with Kazuya's lightning and sound, and bounds on d+2, f+4 and f,f+4.
- **Tag combos for every added fighter.** Their launchers take the tag as Tekken Tag Tournament 2's own fighters' do: tag in the middle of the combo and the partner carries on. Eliza's and Fahkumram's now use their own animations, and Akuma's f,f+2,1 no longer needs Tag held.

### Ultimate Launcher

- **Tekken 8.** The fighters list has a part for each game. Reina is added without Tekken 7 or any of its fighters. If one of the games is uninstalled, the launcher says so and offers to remove that game's fighters all at once.
- **Input delay** in Settings, which now has a **Game** section: off by default, on for the Wii U version's two frames.

## [0.2.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.2.0) - 2026-10-24

The added Tekken 7 fighters get their **preset outfits**, **cloth that swings** and many **move fixes**. **Ultimate Launcher** now tells you which fighters need an update to get them.

### The added fighters

- **Tekken 7's preset outfits.** The costume chooser lists each added fighter's Tekken 7 preset outfits: 4 to 10 per fighter, 137 in all. Contributed by DeReggie (#10).
- **Cloth that swings.** Leroy's jacket, Claudio's coat, Master Raven's ribbons, Noctis's jacket tails and Shaheen's robe and headscarf were rigid. They now swing like Lars's coat tails.
- **Back rolls and missing moves.** Every added fighter can back roll from all four positions on the ground. They also get Tekken 7's shared crouching and running moves, and some strings that never came out now do. Contributed by DeReggie (#8).
- **Special cancels for Akuma and Eliza.** Normal moves cancel into specials, with the motion buffered. Eliza gets her missing inputs, jumping divekicks and EX routes back. (#8)
- **More Tag Assault strings:** Fahkumram's f+3,2,3, Noctis's d/f+4 follow-ups and Kunimitsu's f+4~F into SET. (#8)
- **Balance changes.** Bounds are added or removed for Akuma, Eliza, Fahkumram and Noctis. Akuma's d/f+1+2 and f,f+4 come out in 16 frames, cancel windows are longer, and Fahkumram's b+1 reaches lower. (#8)
- **Portraits blend in.** On the select screen, an added fighter's big portrait fades into the background towards the frame like everyone else's, instead of being cut off at the edge.

### Ultimate Launcher

- **Fighters to update.** Fighters added with an older version show **Update ready**, with **Update** next to **Remove**. **Update All** above the list updates them all at once. If you cancel, the fighters not yet updated keep their old version.
- Adding a fighter takes a few minutes, because its outfits are made along with it.

## [0.1.1](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.1.1) - 2026-10-23

A fix release of **Ultimate Launcher**: installing the game now works on processors without AVX-512, such as the **Steam Deck**.

- **Install works on the Steam Deck and other processors without AVX-512.** In 0.1.0, building the game stopped right away with "Exit code 132" on many processors (the Steam Deck's Zen 2, AMD Ryzen before the 7000 series, most Intel desktop processors): the launcher's build tools contained instructions those processors do not have. They no longer do, and every release is now checked for them.
- **Clearer errors.** When something the launcher runs crashes, the message now says why (for example "Illegal instruction") instead of only a code.

## [0.1.0](https://github.com/Petexy/Golden-Fist-Launcher/releases/tag/v0.1.0) - 2026-10-23

The first release of **Ultimate Launcher**. It allows to install **Tekken Tag Tournament 2** from your own copy of the Wii U game (EU rev 1) and run it natively on Linux, with 120 frames per second, higher resolutions and the Tekken 7 fighters the game lacks.
