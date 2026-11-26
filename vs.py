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


def style(brand, w, h, big=False, align=None, mult=None, margin_frac=None):
    """ASS style. libass treats SRT as a 288-line-high canvas, so convert pixels -> that space.
    Alignment (SSA numbering): 2 bottom, 6 top, 10 middle."""
    k = 288 / h
    m = mult if mult else (1.45 if big else 1.0)
    px = brand.get("caption_size", 62) * m * (min(w, h) / 1080)
    mf = margin_frac if margin_frac is not None else (0 if big else 0.14)
    al = align if align else (10 if big else 2)
    return (f"FontName={brand.get('font','Arial')},FontSize={px * k:.1f},Bold=1,"
            f"PrimaryColour={ass_color(brand.get('fg','#FFFFFF'))},"
            f"OutlineColour={ass_color(brand.get('outline','#000000'))},"
            f"BorderStyle=1,Outline=1.4,Shadow=0.6,Alignment={al},"
            f"MarginV={h * mf * k:.0f},MarginL={int(w * 0.06 * k)},MarginR={int(w * 0.06 * k)}")


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
GRADES = {
    "warm":   "eq=contrast=1.06:saturation=1.18,colorbalance=rs=0.06:gs=0.01:bs=-0.06:rm=0.04:bm=-0.04",
    "cinema": "eq=contrast=1.14:saturation=0.92:gamma=0.96,colorbalance=rs=-0.03:bs=0.05:rh=0.05:bh=-0.03,vignette=PI/5",
    "bright": "eq=brightness=0.04:contrast=1.05:saturation=1.22",
    "punch":  "eq=contrast=1.12:saturation=1.3,unsharp=5:5:0.6",
}
LOGO_POS = {"br": "W-w-40:H-h-40", "bl": "40:H-h-40", "tr": "W-w-40:40", "tl": "40:40"}


def fx_from(a, brand=None):
    """Collect the 'professional' options from CLI args."""
    cta = getattr(a, "cta", None)
    if cta == "site" and brand:
        cta = brand.get("site", "")
    return {"grade": getattr(a, "grade", None), "logo": getattr(a, "logo", None),
            "logo_pos": getattr(a, "logo_pos", "br"), "logo_size": getattr(a, "logo_size", 0.2),
            "hook": getattr(a, "hook", None), "cta": cta,
            "fade": getattr(a, "fade", False), "normalize": getattr(a, "normalize", False)}


def finish(video, out, total, w, h, brand, voice=None, music=None, srt=None, big_captions=False,
           music_vol=0.12, fx=None):
    need("ffmpeg")
    fx = fx or {}
    tmp = Path(tempfile.mkdtemp(prefix="vs_"))
    try:
        shutil.copy(video, tmp / "in.mp4")
        cmd = ["ffmpeg", "-y", "-i", "in.mp4"]
        idx = 1
        voice_i = music_i = logo_i = None
        if voice:
            shutil.copy(voice, tmp / "voice"); cmd += ["-i", "voice"]; voice_i = idx; idx += 1
        if music:
            shutil.copy(music, tmp / "music"); cmd += ["-stream_loop", "-1", "-i", "music"]; music_i = idx; idx += 1
        if fx.get("logo"):
            if not Path(fx["logo"]).exists():
                sys.exit(f"Logo file nahi mili: {fx['logo']}")
            shutil.copy(fx["logo"], tmp / "logo.png"); cmd += ["-loop", "1", "-i", "logo.png"]; logo_i = idx; idx += 1

        fc, cur = [], "0:v"
        # --- video chain: grade + fades, logo, then text on top ---
        pre = []
        if fx.get("grade"):
            if fx["grade"] not in GRADES:
                sys.exit(f"Grade options: {', '.join(GRADES)}")
            pre.append(GRADES[fx["grade"]])
        if fx.get("fade"):
            pre.append(f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(total - 0.5, 0):.2f}:d=0.5")
        if pre:
            fc.append(f"[{cur}]{','.join(pre)}[v1]"); cur = "v1"
        if logo_i:
            fc.append(f"[{logo_i}:v]scale={int(w * fx.get('logo_size', 0.2))}:-1[lg]")
            fc.append(f"[{cur}][lg]overlay={LOGO_POS.get(fx.get('logo_pos', 'br'), LOGO_POS['br'])}[v2]"); cur = "v2"
        subs = []
        if srt:
            (tmp / "subs.srt").write_text(srt, encoding="utf-8")
            subs.append(f"subtitles=subs.srt:force_style='{style(brand, w, h, big_captions)}'")
        if fx.get("hook"):
            end = min(2.8, max(total / 2, 0.8))
            (tmp / "hook.srt").write_text(f"1\n{ts(0.2)} --> {ts(end)}\n{fx['hook']}\n", encoding="utf-8")
            subs.append(f"subtitles=hook.srt:force_style='{style(brand, w, h, align=6, mult=1.5, margin_frac=0.12)}'")
        if fx.get("cta"):
            start = max(total - 3.2, total / 2)
            (tmp / "cta.srt").write_text(f"1\n{ts(start)} --> {ts(total)}\n{fx['cta']}\n", encoding="utf-8")
            subs.append(f"subtitles=cta.srt:force_style='{style(brand, w, h, align=2, mult=1.35, margin_frac=0.22)}'")
        if subs:
            fc.append(f"[{cur}]{','.join(subs)}[v3]"); cur = "v3"

        # --- audio chain ---
        alabel, a_filter = None, False
        if voice_i and music_i:
            fc.append(f"[{voice_i}:a]volume=1.0[va];[{music_i}:a]volume={music_vol}[ma];"
                      f"[va][ma]amix=inputs=2:duration=first:normalize=0[a]"); alabel, a_filter = "a", True
        elif voice_i:
            alabel = f"{voice_i}:a"
        elif music_i:
            fc.append(f"[{music_i}:a]volume={music_vol * 3}[a]"); alabel, a_filter = "a", True
        if alabel:
            post = []
            if fx.get("normalize"):
                post.append("loudnorm=I=-16:TP=-1.5:LRA=11")
            if fx.get("fade"):
                post.append(f"afade=t=in:st=0:d=0.4,afade=t=out:st={max(total - 0.5, 0):.2f}:d=0.5")
            if post:
                fc.append(f"[{alabel}]{','.join(post)}[af]"); alabel, a_filter = "af", True

        if fc:
            cmd += ["-filter_complex", ";".join(fc)]
        cmd += ["-map", f"[{cur}]" if cur != "0:v" else "0:v"]
        if alabel:
            cmd += ["-map", f"[{alabel}]" if a_filter else alabel, "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-t", f"{total:.3f}", "-movflags", "+faststart", str(Path(out).resolve())]
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
        finish(joined, a.out, total, w, h, brand, a.voice, a.music, resolve_captions(a.captions, total), fx=fx_from(a, brand))
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
        joined = tmp / "joined.mp4"
        paths = [tmp / f"c{i}.mp4" for i in range(len(a.clips))]
        if a.xfade > 0 and len(paths) > 1:
            durs = [duration(p) for p in paths]
            x = min(a.xfade, min(durs) / 2 - 0.05)
            if x < a.xfade:
                print(f"Note: clip chhoti hai, transition {x:.2f} sec rakha.")
            fcx, prev, acc = [], "0:v", 0.0
            for k in range(1, len(paths)):
                acc += durs[k - 1]
                lbl = f"x{k}"
                fcx.append(f"[{prev}][{k}:v]xfade=transition={a.transition}:duration={x:.3f}:offset={acc - k * x:.3f}[{lbl}]")
                prev = lbl
            cmdx = ["ffmpeg", "-y"]
            for p in paths:
                cmdx += ["-i", str(p)]
            run(cmdx + ["-filter_complex", ";".join(fcx), "-map", f"[{prev}]", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(joined)])
        else:
            (tmp / "list.txt").write_text("\n".join(lines))
            run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"), "-c", "copy", str(joined)])
        total = duration(a.voice) if a.voice else duration(joined)
        # if voice is longer than video, loop the video to cover it
        if duration(joined) < total:
            looped = tmp / "looped.mp4"
            run(["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(joined), "-t", f"{total:.3f}", "-c", "copy", str(looped)])
            joined = looped
        finish(joined, a.out, total, w, h, brand, a.voice, a.music, resolve_captions(a.captions, total), fx=fx_from(a, brand))
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
        finish(bg, a.out, total, w, h, brand, a.voice, a.music, srt, big_captions=True, fx=fx_from(a, brand))
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
        s.add_argument("--grade", choices=list(GRADES), help="color look: warm / cinema / bright / punch")
        s.add_argument("--logo", help="logo.png (transparent best) watermark")
        s.add_argument("--logo-pos", default="br", choices=list(LOGO_POS), help="br/bl/tr/tl")
        s.add_argument("--logo-size", type=float, default=0.2, help="logo width, frame ka fraction (0.2)")
        s.add_argument("--hook", help="shuru ke 2.5 sec me upar bada text")
        s.add_argument("--cta", help="aakhir ke 3 sec ka text; 'site' likho to brand ki website")
        s.add_argument("--fade", action="store_true", help="shuru/ant me fade in-out")
        s.add_argument("--normalize", action="store_true", help="awaaz ki loudness barabar (-16 LUFS)")

    s = sp.add_parser("slideshow"); s.add_argument("--images", nargs="+", required=True)
    s.add_argument("--sec", type=float, default=4, help="har image kitne sec (voice ho to auto)"); common(s); s.set_defaults(f=cmd_slideshow)
    s = sp.add_parser("reel"); s.add_argument("--clips", nargs="+", required=True)
    s.add_argument("--xfade", type=float, default=0, help="clips ke beech transition (sec), jaise 0.5")
    s.add_argument("--transition", default="fade", help="fade, dissolve, wipeleft, slideleft, circleopen, ...")
    common(s); s.set_defaults(f=cmd_reel)
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
