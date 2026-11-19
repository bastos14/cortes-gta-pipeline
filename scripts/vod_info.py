#!/usr/bin/env python3
"""Lê o info.json do yt-dlp e imprime 'epoch duracao' do VOD (início do VOD em UTC)."""
import json, re, sys, datetime
i = json.load(open(sys.argv[1], encoding="utf-8"))
ts = i.get("timestamp")
if not ts:  # fallback: a URL HLS da Kick traz AAAA/MM/DD/HH/MM do início
    for f in i.get("formats") or []:
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/(\d{2})/(\d{2})/", f.get("url", ""))
        if m:
            ts = datetime.datetime(*map(int, m.groups()), tzinfo=datetime.timezone.utc).timestamp()
            break
print(f"{ts or 0} {i.get('duration') or 0}")
