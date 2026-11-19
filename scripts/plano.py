#!/usr/bin/env python3
"""Divide a análise em blocos (matrix do Actions). Uso: plano.py DUR_VOD INICIO DURACAO BLOCO_S -> JSON"""
import json, sys
dur_vod, ini, dur, bloco = (float(x) for x in sys.argv[1:5])
fim = min(ini + dur, dur_vod) if dur > 0 and dur_vod else (dur_vod or ini + dur)
blocos, t, i = [], ini, 0
while t < fim - 20:
    d = min(bloco, fim - t)
    blocos.append({"i": i, "inicio": int(t), "duracao": int(d)})
    t += bloco; i += 1
print(json.dumps({"include": blocos}))
