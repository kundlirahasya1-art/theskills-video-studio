#!/usr/bin/env python3
"""theskills-video-studio: free video maker (FFmpeg + Python standard library only).

Subcommands:
  slideshow  images (+ voice/music/captions) -> video with slow zoom (Ken Burns)
  reel       video clips joined into one 9:16 (or 16:9) video (+ voice/music/captions)
  textcards  big-text cards on a colour background (+ voice/music)
  shorts     cut one long video into many short vertical clips
  captions   turn a plain-text script into an .srt (timed to a given duration or audio)

Run `python3 vs.py <subcommand> -h` for options. Needs: ffmpeg, ffprobe, python3.
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
FPS = 30


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg error:\n" + " ".join(map(str, cmd)) + "\n" + r.stderr[-1500:])
    return r


def need(tool):
    if not shutil.which(tool):
        sys.exit(f"'{tool}' nahi mila. Mac par: brew install ffmpeg")


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(r.stdout.strip())


def load_brand(name):
    if not name:
        return {"font": "Arial", "caption_size": 64, "bg": "#101828", "fg": "#FFFFFF", "outline": "#000000"}
    p = HERE / "brands" / f"{name}.json"
    if not p.exists():
        sys.exit(f"Brand '{name}' nahi mila. Available: " + ", ".join(x.stem for x in (HERE / "brands").glob("*.json")))
    return json.loads(p.read_text(encoding="utf-8"))


def ass_color(hexcol):
    h = hexcol.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def style(brand, w, h, big=False):
    """ASS style. libass treats SRT as a 288-line-high canvas, so convert pixels -> that space."""
    k = 288 / h
    px = brand.get("caption_size", 62) * (1.45 if big else 1.0) * (min(w, h) / 1080)
    margin_px = 0 if big else h * 0.14
    return (f"FontName={brand.get('font','Arial')},FontSize={px * k:.1f},Bold=1,"
            f"PrimaryColour={ass_color(brand.get('fg','#FFFFFF'))},"
            f"OutlineColour={ass_color(brand.get('outline','#000000'))},"
            f"BorderStyle=1,Outline=1.4,Shadow=0.6,Alignment={10 if big else 2},"
            f"MarginV={margin_px * k:.0f},MarginL={int(w * 0.06 * k)},MarginR={int(w * 0.06 * k)}")


# ---------- captions ----------
def ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def script_to_srt(text, total, max_words=6):
    """Split script into short phrases, time them in proportion to their length."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?।])\s+|\n+", text) if p.strip()]
    chunks = []
    for p in parts:
        words = p.split()
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i:i + max_words]))
    if not chunks:
        sys.exit("Script khali hai.")
    weights = [max(len(c), 4) for c in chunks]
    scale = total / sum(weights)
    t, out = 0.0, []
    for i, (c, wgt) in enumerate(zip(chunks, weights), 1):
        d = wgt * scale
        out.append(f"{i}\n{ts(t)} --> {ts(t + d)}\n{c}\n")
        t += d
    return "\n".join(out)


def resolve_captions(arg, total):
    """arg is .srt (used as is) or .txt script (timed over `total` seconds). Returns srt text or None."""
    if not arg:
        return None
    p = Path(arg)
    if not p.exists():
        sys.exit(f"Captions file nahi mila: {arg}")
    txt = p.read_text(encoding="utf-8")
    return txt if p.suffix.lower() == ".srt" else script_to_srt(txt, total)


# ---------- final mux ----------
def finish(video, out, total, w, h, brand, voice=None, music=None, srt=None, big_captions=False, music_vol=0.12):
    need("ffmpeg")
    tmp = Path(tempfile.mkdtemp(prefix="vs_"))
    try:
        vin = tmp / "in.mp4"
        shutil.copy(video, vin)
        cmd = ["ffmpeg", "-y", "-i", "in.mp4"]
        idx = 1
        voice_i = music_i = None
        if voice:
            shutil.copy(voice, tmp / "voice" ); cmd += ["-i", "voice"]; voice_i = idx; idx += 1
        if music:
            shutil.copy(music, tmp / "music"); cmd += ["-stream_loop", "-1", "-i", "music"]; music_i = idx; idx += 1
        vf = []
        if srt:
            (tmp / "subs.srt").write_text(srt, encoding="utf-8")
            vf.append(f"subtitles=subs.srt:force_style='{style(brand, w, h, big_captions)}'")
        cmd += ["-filter_complex"]
        fc = []
        vlabel = "0:v"
        if vf:
            fc.append(f"[0:v]{','.join(vf)}[v]"); vlabel = "v"
        alabel = None
        if voice_i and music_i:
            fc.append(f"[{voice_i}:a]volume=1.0[va];[{music_i}:a]volume={music_vol}[ma];[va][ma]amix=inputs=2:duration=first:normalize=0[a]"); alabel = "a"
        elif voice_i:
            alabel = f"{voice_i}:a"
        elif music_i:
            fc.append(f"[{music_i}:a]volume={music_vol * 3}[a]"); alabel = "a"
        cmd += [";".join(fc) if fc else "null"]
        cmd += ["-map", f"[{vlabel}]" if vlabel == "v" else "0:v"]
        if alabel:
            cmd += ["-map", f"[{alabel}]" if alabel == "a" else alabel, "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-t", f"{total:.3f}", "-movflags", "+faststart", str(Path(out).resolve())]
        # if no filter at all, drop the dummy -filter_complex
        if not fc:
            i = cmd.index("-filter_complex"); del cmd[i:i + 2]
        run(cmd, cwd=tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"Ban gaya: {out}  ({total:.1f} sec)")


def ensure_out(args):
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)


# ---------- subcommands ----------
def cmd_captions(a):
    total = a.seconds or (duration(a.audio) if a.audio else None)
    if not total:
        sys.exit("--seconds ya --audio do.")
    Path(a.out).write_text(script_to_srt(Path(a.script).read_text(encoding="utf-8"), total, a.words), encoding="utf-8")
    print(f"SRT bana: {a.out}")


def cmd_slideshow(a):
    need("ffmpeg"); ensure_out(a)
    w, h = ASPECTS[a.aspect]; brand = load_brand(a.brand)
    imgs = a.images
    total = duration(a.voice) if a.voice else a.sec * len(imgs)
    per = total / len(imgs)
    frames = max(int(per * FPS), 2)
    tmp = Path(tempfile.mkdtemp(prefix="vs_clips_"))
    try:
        listf = tmp / "list.txt"; lines = []
        for i, img in enumerate(imgs):
            o = tmp / f"c{i}.mp4"
            zin = "min(zoom+0.0007,1.18)" if i % 2 == 0 else "if(eq(on,0),1.18,max(zoom-0.0007,1.0))"
            vf = (f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,crop={w*2}:{h*2},"
                  f"zoompan=z='{zin}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},format=yuv420p")
            run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-vf", vf, "-frames:v", str(frames),
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(o)])
            lines.append(f"file '{o}'")
        listf.write_text("\n".join(lines))
        joined = tmp / "joined.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c", "copy", str(joined)])
        finish(joined, a.out, total, w, h, brand, a.voice, a.music, resolve_captions(a.captions, total))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_reel(a):
    need("ffmpeg"); ensure_out(a)
    w, h = ASPECTS[a.aspect]; brand = load_brand(a.brand)
    tmp = Path(tempfile.mkdtemp(prefix="vs_clips_"))
    try:
        lines = []
        for i, clip in enumerate(a.clips):
            o = tmp / f"c{i}.mp4"
            vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},format=yuv420p"
            run(["ffmpeg", "-y", "-i", clip, "-an", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(o)])
            lines.append(f"file '{o}'")
        (tmp / "list.txt").write_text("\n".join(lines))
        joined = tmp / "joined.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-c", "copy", str(joined)])
        total = duration(a.voice) if a.voice else duration(joined)
        # if voice is longer than video, loop the video to cover it
        if duration(joined) < total:
            looped = tmp / "looped.mp4"
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(joined), "-t", f"{total:.3f}", "-c", "copy", str(looped)])
            joined = looped
        finish(joined, a.out, total, w, h, brand, a.voice, a.music, resolve_captions(a.captions, total))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_textcards(a):
    need("ffmpeg"); ensure_out(a)
    w, h = ASPECTS[a.aspect]; brand = load_brand(a.brand)
    text = Path(a.script).read_text(encoding="utf-8")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    total = duration(a.voice) if a.voice else a.sec * len(lines)
    per = total / len(lines)
    srt = "\n".join(f"{i}\n{ts(i*per - per)} --> {ts(i*per)}\n{l}\n" for i, l in enumerate(lines, 1))
    tmp = Path(tempfile.mkdtemp(prefix="vs_bg_"))
    try:
        bg = tmp / "bg.mp4"
        col = brand.get("bg", "#101828").lstrip("#")
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x{col}:s={w}x{h}:r={FPS}:d={total:.3f}",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(bg)])
        finish(bg, a.out, total, w, h, brand, a.voice, a.music, srt, big_captions=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_shorts(a):
    need("ffmpeg"); Path(a.outdir).mkdir(parents=True, exist_ok=True)
    w, h = ASPECTS["9:16"]
    total = duration(a.input)
    n = int((total - a.start) // a.seg)
    if a.count:
        n = min(n, a.count)
    print(f"{total/60:.1f} min ki video se {n} short bana raha hoon ({a.seg} sec har ek).")
    for i in range(n):
        o = Path(a.outdir) / f"short_{i+1:03}.mp4"
        if a.blur:   # full frame on top of blurred copy (no cropping of people/text)
            fc = (f"[0:v]split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:5[bg];"
                  f"[b]scale={w}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS},format=yuv420p[v]")
        else:
            fc = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},format=yuv420p[v]"
        run(["ffmpeg", "-y", "-ss", f"{a.start + i*a.seg:.2f}", "-t", str(a.seg), "-i", a.input,
             "-filter_complex", fc, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", "21", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(o)])
        print(f"  {o.name}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("--voice", help="voice-over audio (mp3/wav/m4a)")
        s.add_argument("--music", help="background music (low volume)")
        s.add_argument("--captions", help=".txt script (auto-timed) ya .srt")
        s.add_argument("--brand", help="brands/<naam>.json (kundlirahasya, easymeds, theskills)")
        s.add_argument("--aspect", default="9:16", choices=ASPECTS)
        s.add_argument("--out", default="output/video.mp4")

    s = sp.add_parser("slideshow"); s.add_argument("--images", nargs="+", required=True)
    s.add_argument("--sec", type=float, default=4, help="har image kitne sec (voice ho to auto)"); common(s); s.set_defaults(f=cmd_slideshow)
    s = sp.add_parser("reel"); s.add_argument("--clips", nargs="+", required=True); common(s); s.set_defaults(f=cmd_reel)
    s = sp.add_parser("textcards"); s.add_argument("--script", required=True, help="har line ek card")
    s.add_argument("--sec", type=float, default=3); common(s); s.set_defaults(f=cmd_textcards)
    s = sp.add_parser("shorts"); s.add_argument("--input", required=True); s.add_argument("--outdir", default="output/shorts")
    s.add_argument("--seg", type=int, default=45); s.add_argument("--start", type=float, default=0)
    s.add_argument("--count", type=int, help="max kitne shorts"); s.add_argument("--blur", action="store_true", help="blur background, poori frame dikhao")
    s.set_defaults(f=cmd_shorts)
    s = sp.add_parser("captions"); s.add_argument("--script", required=True); s.add_argument("--seconds", type=float)
    s.add_argument("--audio"); s.add_argument("--words", type=int, default=6); s.add_argument("--out", default="output/captions.srt")
    s.set_defaults(f=cmd_captions)
    a = p.parse_args(); need("ffprobe"); a.f(a)


if __name__ == "__main__":
    main()
