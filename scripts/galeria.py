#!/usr/bin/env python3
"""Junta os blocos, escolhe o top N global (sem sobreposição) e monta a galeria de aprovação.
Entrada: blocos/<bloco-i>/{picos.json,previas/clip_*.mp4}. Saída: galeria/{index.html,picos_final.json,clips/}"""
import argparse, glob, html, json, os, shutil
ap = argparse.ArgumentParser()
ap.add_argument("--blocos", default="blocos"); ap.add_argument("--saida", default="galeria")
ap.add_argument("--top", type=int, default=10); ap.add_argument("--meta", default="{}")
a = ap.parse_args()
meta = json.loads(a.meta)
cands = []
for f in glob.glob(os.path.join(a.blocos, "*", "picos.json")):
    d = os.path.dirname(f)
    for p in json.load(open(f, encoding="utf-8"))["top"]:
        p["_clip"] = os.path.join(d, "previas", f"clip_{int(p['inicio_s'])}.mp4")
        cands.append(p)
cands.sort(key=lambda p: -p["nota"])
escolhidos = []
for p in cands:
    if all(p["fim_s"] + 8 <= q["inicio_s"] or p["inicio_s"] >= q["fim_s"] + 8 for q in escolhidos) and os.path.exists(p["_clip"]):
        escolhidos.append(p)
    if len(escolhidos) >= a.top:
        break
os.makedirs(os.path.join(a.saida, "clips"), exist_ok=True)
for n, p in enumerate(escolhidos, 1):
    p["id"] = n
    p["arquivo"] = f"clips/{n:02d}.mp4"
    shutil.copy(p.pop("_clip"), os.path.join(a.saida, p["arquivo"]))
json.dump({"meta": meta, "top": escolhidos}, open(os.path.join(a.saida, "picos_final.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

def card(p):
    return f"""<article class="card"><video controls preload="metadata" src="{p['arquivo']}"></video>
<div class="info"><label class="ok"><input type="checkbox" value="{p['id']}"> Aprovar #{p['id']}</label>
<h2>#{p['id']} · nota {p['nota']:.0f} · {p['inicio_hms']}–{p['fim_hms']} ({p['duracao_s']:.0f}s)</h2>
<p class="motivo">{html.escape(p['motivo'])}</p>
<p class="fala">“{html.escape(p['trecho_falado'][:260])}…”</p></div></article>"""

page = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Galeria de aprovação</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--card:#f3f3f3;--mut:#555;--ac:#0a6cff}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--card:#1d1d1d;--mut:#aaa;--ac:#5aa2ff}}}}
body{{background:var(--bg);color:var(--fg);font:16px system-ui;margin:0;padding:16px;max-width:980px;margin-inline:auto}}
.card{{background:var(--card);border-radius:12px;padding:12px;margin:12px 0;display:grid;gap:12px;grid-template-columns:minmax(0,320px) 1fr}}
@media(max-width:700px){{.card{{grid-template-columns:1fr}}}}video{{width:100%;border-radius:8px;background:#000}}
h2{{font-size:1rem;margin:.4rem 0}}.motivo{{margin:.2rem 0}}.fala{{color:var(--mut);font-size:.9rem}}
.ok{{font-weight:600}}button{{background:var(--ac);color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:1rem}}
#res{{font-family:monospace}}.regras{{background:var(--card);border-radius:12px;padding:12px}}</style></head><body>
<h1>Galeria de aprovação</h1>
<p>{html.escape(str(meta.get('streamer','')))} · VOD {html.escape(str(meta.get('vod','')))} · {len(escolhidos)} candidatos · execução {html.escape(str(meta.get('run','')))}</p>
<div class="regras"><b>Confira antes de aprovar:</b> o Allan participa ativamente (regra 1) · sem familiares dele (regra 29) · sem marcas/apostas/links (regras 17–18) · sem spoiler ou música alta de GTA · a abertura não distorce o que aconteceu (regra 8).</div>
{''.join(card(p) for p in escolhidos)}
<p><button onclick="g()">Gerar lista de aprovados</button></p><p id="res"></p>
<script>function g(){{const v=[...document.querySelectorAll('input:checked')].map(i=>i.value).join(',');
document.getElementById('res').textContent=v?('aprovados: '+v+'  (execução {html.escape(str(meta.get('run','')))})'):'nenhum selecionado'}}</script></body></html>"""
open(os.path.join(a.saida, "index.html"), "w", encoding="utf-8").write(page)
print(f"{'#':>2} {'início':>8} {'nota':>5}  motivo")
for p in escolhidos:
    print(f"{p['id']:>2} {p['inicio_hms']:>8} {p['nota']:>5.0f}  {p['motivo'][:110]}")
