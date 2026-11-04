"""captions.json → subs.ass + subs.srt, затем сборка MP4 1080×1920 с вожжёнными субтитрами."""
import json
import re
import subprocess
import sys

J = "/Users/andreyafanasyev/.claude/jobs/0653a80b/tmp"
OUT = sys.argv[1]
# libass не рисует цветные эмодзи — убираем их из субтитров.
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿️]")


def clean(text: str) -> str:
    return re.sub(r"\s{2,}", " ", EMOJI.sub("", text)).strip()


def ts_ass(ms: int) -> str:
    cs = ms // 10
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def ts_srt(ms: int) -> str:
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


caps = json.load(open(f"{J}/captions.json"))
events = [(c["t"], caps[i + 1]["t"], clean(c["text"])) for i, c in enumerate(caps[:-1]) if c["text"]]

ass = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
# Центр полосы субтитров (y 1620…1920) — \pos(540,1770).
ass += "".join(f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},Default,,0,0,0,,{{\\pos(540,1770)}}{t}\n" for a, b, t in events)
open(f"{J}/subs.ass", "w").write(ass)
open(f"{J}/subs.srt", "w").write("\n".join(f"{i}\n{ts_srt(a)} --> {ts_srt(b)}\n{t}\n" for i, (a, b, t) in enumerate(events, 1)))

subprocess.run([
    "ffmpeg", "-v", "error", "-y",
    "-f", "concat", "-safe", "0", "-i", f"{J}/frames.txt",
    "-f", "lavfi", "-i", "color=c=0x1F3A24:s=1080x1920:r=30",
    "-filter_complex",
    "[0:v]fps=30,scale=780:1560,setsar=1[p];"
    "[1:v]drawbox=x=146:y=36:w=788:h=1568:color=0x44C24A:t=4[bg];"
    f"[bg][p]overlay=150:40:shortest=1,subtitles={J}/subs.ass[v]",
    "-map", "[v]", "-c:v", "libx264", "-preset", "slow", "-crf", "20", "-pix_fmt", "yuv420p",
    "-movflags", "+faststart", OUT,
], check=True)
print("ok", OUT, len(events), "subtitles")
