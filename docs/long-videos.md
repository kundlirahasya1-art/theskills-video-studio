# Lambi videos (1-3 ghante)

1. Voice-over record karo (ya script padhkar). Ek hi lambi file: `input/voice.mp3`.
2. Photos/slides ki list banao. Jitni zyada utni achhi, har ek 5-15 sec dikhegi.
3. Chalao:
   ```bash
   python3 vs.py slideshow --images input/*.jpg --voice input/voice.mp3 \
     --music input/music.mp3 --aspect 16:9 --brand theskills --out output/long.mp4
   ```
   Har photo ka time = voice ki lambai / photo ki ginti. 1 ghante = 3600 sec, 240 photo -> har ek 15 sec.
4. Lambi video se shorts: `python3 vs.py shorts --input output/long.mp4 --seg 45 --count 30 --blur`

Tip: pehle 60 sec ka test chalao, phir poora. Lambi video me Mac thoda garam ho sakta hai, charger lagao.

Time ka andaaza (naapa hua): 5 min ki 1080p slideshow ~5 min me bani. Isliye 1 ghante ki video ~1 ghanta lagegi. Jaldi chahiye to `--aspect 9:16` (chhota frame) ya kam photos use karo.
