# Pakki caption timing (optional): Whisper

Auto-timing (script ke hisaab se) andaaza hai. Asli bolne wali awaaz se exact timing chahiye to Mac par Whisper lagao
(free, local, internet se ek baar install):

```bash
pip3 install openai-whisper          # ya: pip3 install mlx-whisper  (Apple chip par tez)
whisper input/voice.mp3 --language Hindi --model small --output_format srt --output_dir output
```
Phir:
```bash
python3 vs.py slideshow --images ... --voice input/voice.mp3 --captions output/voice.srt --brand kundlirahasya
```
Hindi ke liye `small` ya `medium` model achha hai. Naam/shabd galat aaye to .srt file text editor me theek kar lo.
