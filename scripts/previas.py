#!/usr/bin/env python3
"""Gera prévias curtas (baixa resolução) dos picos de um bloco. Nome: clip_<inicio_s>.mp4"""
import argparse, json, os, subprocess
ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True); ap.add_argument("--picos", required=True)
ap.add_argument("--offset", type=float, default=0); ap.add_argument("--saida", required=True)
a = ap.parse_args()
os.makedirs(a.saida, exist_ok=True)
for p in json.load(open(a.picos, encoding="utf-8"))["top"]:
    out = os.path.join(a.saida, f"clip_{int(p['inicio_s'])}.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(max(0, p["inicio_s"] - a.offset)),
                    "-t", str(p["duracao_s"]), "-i", a.video, "-vf", "scale=-2:360",
                    "-c:v", "libx264", "-crf", "32", "-preset", "veryfast",
                    "-c:a", "aac", "-b:a", "64k", out], check=True)
print("prévias:", len(os.listdir(a.saida)))
