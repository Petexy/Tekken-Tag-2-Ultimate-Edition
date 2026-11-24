# The launcher's fonts

Unmodified TrueType files from their upstream repositories, under the SIL Open
Font License 1.1 (`OFL.txt` beside each family; neither declares a Reserved Font
Name). They are built into the launcher (`ttt2_launcher_fonts`, see
`cmake/EmbedFiles.cmake`), so no font file is installed beside it.

| Family | Upstream | Commit | Files |
|---|---|---|---|
| Barlow Condensed | https://github.com/jpt/barlow (`fonts/ttf/`) | `dc2940e2e04ef4ec96c07e23e0f02aefbddd343b` | SemiBold, Bold, ExtraBold, Black, BoldItalic, ExtraBoldItalic, BlackItalic |
| Barlow | https://github.com/jpt/barlow (`fonts/ttf/`) | `dc2940e2e04ef4ec96c07e23e0f02aefbddd343b` | Regular, Medium, SemiBold, Bold |
| JetBrains Mono | https://github.com/JetBrains/JetBrainsMono (`fonts/ttf/`) | `19371302b95d218af43299bce79ddbddd0bc364d` | Regular, Bold |

SHA-256 of each file:

```
5943ef8b1b2f7ebb3515df6307d556d536a15cfa4f36783e9d1c2f1bf4058e35  BarlowCondensed/BarlowCondensed-Black.ttf
f8578fb71c42f6d513bfea8ef2dc21eec1a46a13f5246dd85d0a6344155f15ff  BarlowCondensed/BarlowCondensed-BlackItalic.ttf
84b4ccb588c419b8236907d021101bd517d7a05b33d4f0d21ee57ea39f36c885  BarlowCondensed/BarlowCondensed-Bold.ttf
f4862f6f896647c1ad773e662811774cd4d225f939e9aa55f968e143ccbad709  BarlowCondensed/BarlowCondensed-BoldItalic.ttf
fc79e7e0bc036a5471fd6b52b7d8d102062aad00d55a85ce28cc2d0511de5cec  BarlowCondensed/BarlowCondensed-ExtraBold.ttf
86d1f2d671023cfc88dd216bd118039f5942ca01aa48495e491fea51df52c022  BarlowCondensed/BarlowCondensed-ExtraBoldItalic.ttf
31f11ff391c790a36b977fc01e0880656762ac26f6634a0e6ff4f80c7d4c534f  BarlowCondensed/BarlowCondensed-SemiBold.ttf
186d750eb496a4c17a76385f82be6aea2ac1cf2de074a811d63786cf374ea73f  BarlowCondensed/OFL.txt
aeb8c7772bacd65d1a89021f8874762e7747286c85ce23b396ff0c11a89525d3  Barlow/Barlow-Bold.ttf
2f51d2a9de6641d33bc2a7c3e7081c37388587377430cc99c89d0d514c52f687  Barlow/Barlow-Medium.ttf
1da0b65f2389aeafb817e63a18ed30569537bfa9c1d68bb45f12c25691481068  Barlow/Barlow-Regular.ttf
4921fa2882d1835d2f487b3b1121ba483373726c50f92f5381d078846e36f61d  Barlow/Barlow-SemiBold.ttf
186d750eb496a4c17a76385f82be6aea2ac1cf2de074a811d63786cf374ea73f  Barlow/OFL.txt
e6fd0d7e91550b3ed2b735d4312474362c4716edc4fc0577a0f61ed782d5aed1  JetBrainsMono/JetBrainsMono-Regular.ttf
d22c4f3821d725eb01210d278d95dfcfcaadc34699a06658d47c8a5cc5830ada  JetBrainsMono/JetBrainsMono-Bold.ttf
a76abf002c49097d146e86740a3105a5d00450b1592e820a1109a8c5680cd697  JetBrainsMono/OFL.txt
```

The launcher's look uses Barlow Condensed 700/800/900 italic
(and 800 upright) for headings and menu items, Barlow 500/600/700 for body text,
JetBrains Mono for paths, commands and the log. It also asks for Barlow 800 and
JetBrains Mono 500/600 in a few small labels: the nearest weight here stands in,
or the file is added from the same commits.
