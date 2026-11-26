# The launcher's fonts

TrueType files from their upstream repositories, under the SIL Open Font License
1.1 (`OFL.txt` beside each family; none declares a Reserved Font Name). Barlow and
JetBrains Mono are unmodified; Fira Sans is cut to its Cyrillic letters (below). They are built into the launcher (`ttt2_launcher_fonts`, see
`cmake/EmbedFiles.cmake`), so no font file is installed beside it.

| Family | Upstream | Commit | Files |
|---|---|---|---|
| Barlow Condensed | https://github.com/jpt/barlow (`fonts/ttf/`) | `dc2940e2e04ef4ec96c07e23e0f02aefbddd343b` | SemiBold, Bold, ExtraBold, Black, BoldItalic, ExtraBoldItalic, BlackItalic |
| Barlow | https://github.com/jpt/barlow (`fonts/ttf/`) | `dc2940e2e04ef4ec96c07e23e0f02aefbddd343b` | Regular, Medium, SemiBold, Bold |
| JetBrains Mono | https://github.com/JetBrains/JetBrainsMono (`fonts/ttf/`) | `19371302b95d218af43299bce79ddbddd0bc364d` | Regular, Bold |
| Fira Sans Condensed | https://github.com/google/fonts (`ofl/firasanscondensed/`) | `def3b65c3d785d3b917af277975636915b2ad0a1` | BlackItalic, ExtraBoldItalic, BoldItalic, ExtraBold (Cyrillic only) |
| Fira Sans | https://github.com/google/fonts (`ofl/firasans/`) | `def3b65c3d785d3b917af277975636915b2ad0a1` | Medium, SemiBold, Bold (Cyrillic only) |

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
9cc6cdc9c4b14d68747c8f82043283c5b8ea725789c4f22c5ac31e7f33b6ad9a  FiraSans/FiraSans-Bold.ttf
e89f1b9642206782e696f2619169abd73653335f8884c6d394d71e1f70f53e01  FiraSans/FiraSans-Medium.ttf
6eda14fcd9205e0e71f7cfc37df245838d849fcf40cf812f6a5b85263e67fe8d  FiraSans/FiraSans-SemiBold.ttf
d93159148d2ca53d7aa82ccfc9afffd9214c8b5b783f5fa8bcf9db8586bdc4db  FiraSans/FiraSansCondensed-BlackItalic.ttf
8567527d57d35ae18af984511a974cd65cc0ed371dab8bc7469b06a1548e1b52  FiraSans/FiraSansCondensed-BoldItalic.ttf
589e4bc434e46cf876cbef97248bbf4bf0e45b0175fc056bf306f34d7d2e8a21  FiraSans/FiraSansCondensed-ExtraBold.ttf
2c8b98fde827acebfd42821a8d924e1d65c0697092f907d03934c53f234f14e6  FiraSans/FiraSansCondensed-ExtraBoldItalic.ttf
8f24842e9174beda18a556c2ae7d54f5dc444340c19a3a9ef77e23bca366adbd  FiraSans/OFL.txt
e6fd0d7e91550b3ed2b735d4312474362c4716edc4fc0577a0f61ed782d5aed1  JetBrainsMono/JetBrainsMono-Regular.ttf
d22c4f3821d725eb01210d278d95dfcfcaadc34699a06658d47c8a5cc5830ada  JetBrainsMono/JetBrainsMono-Bold.ttf
a76abf002c49097d146e86740a3105a5d00450b1592e820a1109a8c5680cd697  JetBrainsMono/OFL.txt
```

The launcher's look uses Barlow Condensed 700/800/900 italic
(and 800 upright) for headings and menu items, Barlow 500/600/700 for body text,
JetBrains Mono for paths, commands and the log. It also asks for Barlow 800 and
JetBrains Mono 500/600 in a few small labels: the nearest weight here stands in,
or the file is added from the same commits.

Russian: Barlow has no Cyrillic letters, so each role's text draws them with Fira
Sans of a matching width, weight and slant (`theme::kCyrillicFiles`; Barlow's and
Fira's ascent plus descent are the same, 1200 units, so the letters share a
baseline and size). Only the Cyrillic block is kept (U+0400–045F, Ґ ґ, №): about
14 KB a file instead of 500 KB. Made with fontTools 4.68.0 from the upstream files
(SHA-256 below), which gives the files above byte for byte:

```
pyftsubset <file> --unicodes="U+0400-045F,U+0490-0491,U+2116" --no-hinting --name-IDs='*' --output-file=FiraSans/<file>
```

```
cbc1842cbed8c1d1146ba7c9db97d8f28c9bedfd25f41c5b0e1259ca48622328  ofl/firasans/FiraSans-Medium.ttf
db0321f83eb3e9f527b8af384a1b3fefdc1039cf2b06fd39b3f61492bda9561c  ofl/firasans/FiraSans-SemiBold.ttf
a4d8e149ecdd4874a0726eb0af894488b3b31c423d6b0017c8f415ed1b795b45  ofl/firasans/FiraSans-Bold.ttf
8ab2cfe67370b7cc37e8ad24619a6b0510e2467a07d6bc41c6b20da4ca2bf963  ofl/firasanscondensed/FiraSansCondensed-BlackItalic.ttf
071e6c37e90a3ba2fb53ede9f88fd77d024770503665697187013397002b0c66  ofl/firasanscondensed/FiraSansCondensed-ExtraBoldItalic.ttf
aebe32d2d821890e0d66443ca2dc59b237ff34a575048696a96516d857ae0da6  ofl/firasanscondensed/FiraSansCondensed-BoldItalic.ttf
d1e5181a65e04970ef17b83fa518277658217081a032c7f60b7ac0f101347cf2  ofl/firasanscondensed/FiraSansCondensed-ExtraBold.ttf
```
