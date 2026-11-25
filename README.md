# theskills-video-studio

Free video maker for **KundliRahasya, EasyMeds, TheSkills**. Sirf FFmpeg + Python (koi pip install nahi, koi credit nahi).
Mohit ke Mac par / Claude ke saath chalta hai.

## Ye kya karta hai (aur kya nahi)
**Karta hai (free, kitni bhi lambi video):**
- Photos + voice-over -> slow-zoom wali video (`slideshow`)
- Alag-alag clips jodkar 9:16 reel (`reel`)
- Bade text cards wali video, jaise "quote / tip" reels (`textcards`)
- 1-3 ghante ki lambi video se kai chhote vertical shorts kaatna (`shorts`)
- Script se auto-timed captions (`captions`), music + voice mix, brand ke rang/font

**Nahi karta:** nayi "hyper-realistic" AI footage khud nahi banata. Wo Google Flow / Veo jaise AI tools ya
asli shoot / free stock clips (Pexels, Pixabay) se aati hai. Ye repo unhe jodta, kaat-ta, caption lagata hai, isse
credit bachte hain (AI se sirf kuch kaam ki clips lo, baaki sab yahan).

## Install (Mac, ek baar)
```bash
brew install ffmpeg        # python3 Mac me pehle se hota hai
git clone <is repo ka link> && cd theskills-video-studio
python3 vs.py -h
```

## Roz ka kaam
```bash
# 1) Photos + voice + auto captions (script.txt me bolne wala text)
python3 vs.py slideshow --images input/1.jpg input/2.jpg input/3.jpg \
  --voice input/voice.mp3 --captions input/script.txt --brand kundlirahasya --out output/reel1.mp4

# 2) Clips jodo + music
python3 vs.py reel --clips input/a.mp4 input/b.mp4 --music input/music.mp3 \
  --captions input/script.txt --brand easymeds --out output/reel2.mp4

# 3) Text cards (script me har line = ek card)
python3 vs.py textcards --script input/cards.txt --voice input/voice.mp3 --brand theskills --out output/tip1.mp4

# 4) Lambi video -> 45 sec ke 20 shorts (blur background, poori frame dikhti hai)
python3 vs.py shorts --input input/long.mp4 --seg 45 --count 20 --blur

# 5) Sirf SRT chahiye
python3 vs.py captions --script input/script.txt --audio input/voice.mp3 --out output/captions.srt
```
`--aspect 16:9` (YouTube) ya `1:1` bhi chalta hai. Default 9:16.

## Brands
`brands/kundlirahasya.json`, `easymeds.json`, `theskills.json`: rang, font, caption size. Apne hisaab se badlo.
**Hindi captions** ke liye Devanagari font chahiye. Mac par `Kohinoor Devanagari` pehle se hota hai.
Captions kitni sahi timing me aayengi: script se auto-timing andaaza hai. Pakki timing ke liye `docs/whisper.md`.

## Lambi video (1-3 ghante)
Voice-over ki lambi file + bahut saari photos/clips do. FFmpeg ko koi limit nahi, bas time lagta hai
(zoom wali slideshow lagbhag real-time speed se banti hai: 5 min ki 1080p video ~5 min me. 1 ghante ki video ~1 ghanta; Apple chip Mac par aksar tez). Steps: `docs/long-videos.md`.

## Free hyper-realistic ke raaste (honest)
Dekho `docs/realism.md`.
