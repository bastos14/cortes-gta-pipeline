#!/usr/bin/env python3
"""Fase 3: edição final 9:16 dos cortes aprovados.
Tela dividida (streamer em cima / jogo embaixo), frase de abertura no meio, marca d'água do campeonato o corte todo
e legenda palavra a palavra (Whisper maior). Logo própria só se config marcar ativa=true (hoje DESLIGADA)."""
import argparse, json, os, re, subprocess, sys, textwrap
import yaml
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from picos import le_audio, compila_gatilhos, pontos_texto

def ass_t(t):
    t = max(t, 0); h, r = divmod(t, 3600); m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"

def limpa(t):
    return re.sub(r"[{}\\]", "", t).strip()

def transcreve(video, modelo):
    from faster_whisper import WhisperModel
    x = le_audio(video)
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(x, language="pt", vad_filter=True, beam_size=5, word_timestamps=True,
                           condition_on_previous_text=False)
    out = []
    for s in segs:
        out.append({"inicio": float(s.start), "fim": float(s.end), "texto": s.text.strip(),
                    "palavras": [{"w": limpa(w.word), "i": float(w.start), "f": float(w.end)} for w in (s.words or []) if limpa(w.word)]})
    return out

def escolhe_frase(segs, gat, max_pal):
    melhor, nota = None, -1
    for s in segs:
        if len(s["texto"].split()) < 3:
            continue
        pts, _ = pontos_texto(s["texto"], gat)
        pts += min(len(s["texto"].split()), 12) * 0.02 - s["inicio"] * 0.005   # desempate: mais cedo e mais completa
        if pts > nota:
            melhor, nota = s, pts
    if not melhor:
        return ""
    pal = melhor["texto"].replace("...", " ").split()[:max_pal]
    return " ".join(pal).rstrip(",;:-")

def quebra(frase, larg=18):
    return r"\N".join(textwrap.wrap(frase.upper(), larg)[:3])

def gera_ass(cfg, ed, segs, frase, dur, marca):
    W, H, top = ed["largura"], ed["altura"], ed["topo_altura"]
    fonte, dest = ed["fonte"], ed["legenda_cor_destaque"]
    linhas = [f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Legenda,{fonte},76,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,7,0,2,40,40,{ed['legenda_margem_inferior']},1
Style: Frase,{fonte},58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,3,18,0,5,40,40,0,1
Style: Marca,{fonte},46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,5,0,8,40,40,0,1

[Events]
Format: Layer,Start,End,Name,Style,MarginL,MarginR,MarginV,Effect,Text"""]
    fim = ass_t(dur)
    linhas.append(f"Dialogue: 2,{ass_t(0)},{fim},,Marca,0,0,0,,{{\\pos({W//2},{ed['marca_dagua_y']})}}{marca}")
    if frase:
        linhas.append(f"Dialogue: 1,{ass_t(0)},{fim},,Frase,0,0,0,,{{\\pos({W//2},{top})}}{quebra(frase)}")
    n = ed["legenda_palavras_por_bloco"]
    pal = [p for s in segs for p in s["palavras"]]
    blocos, atual = [], []
    for p in pal:
        if atual and (len(atual) >= n or p["i"] - atual[-1]["f"] > 0.8):
            blocos.append(atual); atual = []
        atual.append(p)
        if re.search(r"[.!?]$", p["w"]):
            blocos.append(atual); atual = []
    if atual:
        blocos.append(atual)
    for b in blocos:
        for k, p in enumerate(b):
            ini = p["i"]
            f = b[k + 1]["i"] if k + 1 < len(b) else min(p["f"] + 0.15, dur)
            txt = " ".join((f"{{\\c&H{dest}&}}{q['w'].upper()}{{\\c&HFFFFFF&}}" if j == k else q["w"].upper()) for j, q in enumerate(b))
            linhas.append(f"Dialogue: 0,{ass_t(ini)},{ass_t(f)},,Legenda,0,0,0,,{txt}")
    return "\n".join(linhas) + "\n"

def sonda(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", video], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    return d["streams"][0]["width"], d["streams"][0]["height"], float(d["format"]["duration"])

def par(v):
    return int(v) // 2 * 2

def camera_do_trecho(lay, inicio_s):
    for per in lay.get("camera_periodos") or []:
        if inicio_s < per["ate_s"]:
            return per["camera"]
    return lay["camera"]

def renderiza(video, ass, saida, lay, ed, logo, inicio_s=0):
    W, H, top = ed["largura"], ed["altura"], ed["topo_altura"]
    bot = H - top
    iw, ih, _ = sonda(video)
    c = camera_do_trecho(lay, inicio_s); j = lay["jogo"]
    cw, ch = par(c["w"] * iw), par(c["h"] * ih)
    cx, cy = par(c["x"] * iw), par(c["y"] * ih)
    jh = par(j.get("h", 1.0) * ih); jw = min(par(jh * W / bot), iw)
    jx, jy = min(par(j["x"] * iw), iw - jw), par(j.get("y", 0.0) * ih)
    g = (f"[0:v]split=2[a][b];"
         f"[a]crop={cw}:{ch}:{cx}:{cy},scale={W}:{top}:force_original_aspect_ratio=increase,crop={W}:{top}[t];"
         f"[b]crop={jw}:{jh}:{jx}:{jy},scale={W}:{bot}:force_original_aspect_ratio=increase,crop={W}:{bot}[g];"
         f"[t][g]vstack[v]")
    ent = ["-i", video]
    if logo:
        ent += ["-i", logo]
        g += f";[1:v]scale=220:-1[l];[v][l]overlay=(W-w)/2:{top}-h/2[v]"
    g += f";[v]ass={ass}[o]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ent, "-filter_complex", g, "-map", "[o]", "-map", "0:a?",
                    "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", str(ed["crf"]), "-pix_fmt", "yuv420p",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", saida], check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--picos", required=True, help="galeria/picos_final.json")
    ap.add_argument("--aprovados", default="todos", help="ids separados por vírgula ou 'todos'")
    ap.add_argument("--vod", required=True); ap.add_argument("--streamer", default="allanstag")
    ap.add_argument("--saida", default="cortes"); ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--altura-max", type=int, default=1080, help="altura máxima do vídeo baixado (teste: 480)")
    ap.add_argument("--streamers", default="streamers.yaml"); ap.add_argument("--titulos", default="titulos.yaml")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    st = yaml.safe_load(open(a.streamers, encoding="utf-8"))["streamers"][a.streamer]
    lay = st["layout"]; ed = cfg["edicao"]; camp = cfg["campanha"]
    manual = yaml.safe_load(open(a.titulos, encoding="utf-8")) or {} if os.path.exists(a.titulos) else {}
    gat = compila_gatilhos(cfg["picos"]["palavras_gatilho"])
    logo = None
    mp = cfg.get("marca_dagua_propria", {})
    if mp.get("ativa") and os.path.exists(mp["arquivo"]):
        logo = mp["arquivo"]
    picos = json.load(open(a.picos, encoding="utf-8"))["top"]
    ids = None if a.aprovados.strip().lower() == "todos" else {int(x) for x in a.aprovados.split(",") if x.strip()}
    os.makedirs(a.saida, exist_ok=True); os.makedirs("tmp", exist_ok=True)
    manifesto = []
    for p in picos:
        if ids is not None and p["id"] not in ids:
            continue
        n = f"{p['id']:02d}"; bruto = f"tmp/{n}.mp4"
        print(f"== corte {n}: {p['inicio_hms']} ({p['duracao_s']:.0f}s)", flush=True)
        for f in os.listdir("tmp"):
            if f.startswith(n + "."):
                os.remove(os.path.join("tmp", f))
        subprocess.run(["yt-dlp", "--no-playlist", "--quiet", "--force-keyframes-at-cuts",
                        "--download-sections", f"*{int(p['inicio_s'])}-{int(p['fim_s'])}",
                        "-f", f"bv*[height<={a.altura_max}]+ba/b[height<={a.altura_max}]/best", "--merge-output-format", "mp4",
                        "-o", f"tmp/{n}.%(ext)s", a.vod], check=True)
        _, _, dur = sonda(bruto)
        segs = transcreve(bruto, ed["whisper_modelo_legenda"])
        frase = limpa(str(manual.get(str(int(p["inicio_s"])), ""))) or escolhe_frase(segs, gat, ed["frase_max_palavras"])
        ass = f"tmp/{n}.ass"
        open(ass, "w", encoding="utf-8").write(gera_ass(cfg, ed, segs, frase, dur, camp["marca_dagua_texto"]))
        out = f"{a.saida}/corte_{n}.mp4"
        renderiza(bruto, ass, out, lay, ed, logo, p["inicio_s"])
        titulo = (frase[:1].upper() + frase[1:].lower() if frase else "Momento da live") + " " + camp["hashtag_obrigatoria"]
        manifesto.append({"id": p["id"], "arquivo": out, "vod": a.vod, "inicio_s": p["inicio_s"], "fim_s": p["fim_s"],
                          "duracao_s": round(dur, 1), "frase": frase, "titulo": titulo, "nota": p.get("nota"),
                          "motivo": p.get("motivo"), "logo_propria": bool(logo)})
        os.remove(bruto)
    json.dump(manifesto, open(f"{a.saida}/manifesto.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{'id':>3} {'dur':>5}  frase de abertura | título")
    for m in manifesto:
        print(f"{m['id']:>3} {m['duracao_s']:>5}  {m['frase']} | {m['titulo']}")

if __name__ == "__main__":
    main()
