#!/usr/bin/env python3
"""FASE 1: acha os melhores momentos de um VOD.
Sinais: (a) chat por janela, (b) picos de volume/risada (ffmpeg), (c) gatilhos na transcrição (faster-whisper).
Saída: picos.json com top N (inicio, fim, nota 0-100, motivo). Tempos no relógio do VOD (segundos)."""
import argparse, json, re, subprocess, sys, unicodedata
import numpy as np
import yaml

SR = 16000

# ---------- áudio ----------
def le_audio(video, sr=SR):
    cmd = ["ffmpeg", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

def serie_volume(x, sr=SR):
    """dBFS por segundo + 'estouro' = quanto acima da base local (mediana móvel de 2 min), em dB."""
    n = len(x) // sr
    if n == 0:
        return np.zeros(0), np.zeros(0)
    rms = np.sqrt(np.mean(x[: n * sr].reshape(n, sr) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    base = np.array([np.median(db[max(0, i - 60): i + 60]) for i in range(n)])
    return db, np.maximum(0.0, db - base)

# ---------- transcrição ----------
def transcreve(audio, modelo, idioma="pt"):
    """audio: array float32 mono 16 kHz (evita a decodificação via PyAV)."""
    from faster_whisper import WhisperModel
    m = WhisperModel(modelo, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, language=idioma, vad_filter=True, beam_size=1,
                           condition_on_previous_text=False)
    return [{"inicio": float(s.start), "fim": float(s.end), "texto": s.text.strip()} for s in segs]

def norm(t):
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))

def compila_gatilhos(cfg):
    out = []
    for peso, termos in (cfg or {}).items():
        for t in termos:
            out.append((norm(str(t)), float(peso)))
    return out

def pontos_texto(texto, gatilhos):
    t, pts, achados = norm(texto), 0.0, []
    for termo, peso in gatilhos:
        k = len(re.findall(r"(?<!\w)" + re.escape(termo) + r"(?!\w)", t)) if termo.isalpha() or " " in termo \
            else t.count(termo)
        if k:
            pts += peso * min(k, 3)
            achados.append(termo)
    pts += 0.5 * min(texto.count("!"), 3) + 0.3 * min(texto.count("?"), 2)
    return pts, achados

# ---------- pontuação ----------
def escala(v):
    v = np.asarray(v, dtype=float)
    ref = max(np.percentile(v, 95), 0.5 * v.max(), 1e-9)
    return np.clip(v / ref, 0, 1)

def janelas(dur, janela, passo):
    ini = np.arange(0, max(dur - janela, 0) + 1e-9, passo)
    return ini

def pontua(offset, dur, estouro, mensagens, segmentos, gatilhos, cfg):
    jan, passo = cfg["janela_s"], cfg["passo_s"]
    ini = janelas(dur, jan, passo)
    f_audio = np.zeros(len(ini)); f_chat = np.zeros(len(ini)); f_texto = np.zeros(len(ini))
    detalhe = []
    tmsg = np.array([m["t"] - offset for m in mensagens]) if mensagens else np.zeros(0)
    for i, a in enumerate(ini):
        b = a + jan
        sl = estouro[int(a): int(b)]
        f_audio[i] = np.mean(np.sort(sl)[-5:]) if len(sl) else 0.0  # média dos 5 s mais altos acima da base
        n_msg = int(np.sum((tmsg >= a) & (tmsg < b))) if len(tmsg) else 0
        f_chat[i] = n_msg
        pts, ach, palavras = 0.0, [], 0
        for s in segmentos:
            if s["fim"] > a and s["inicio"] < b:
                p, ac = pontos_texto(s["texto"], gatilhos)
                pts += p; ach += ac; palavras += len(s["texto"].split())
        pts += 0.5 * (palavras / jan)  # ritmo de fala (palavras/s)
        f_texto[i] = pts
        detalhe.append({"msgs": n_msg, "gatilhos": ach, "pico_db": float(np.max(sl)) if len(sl) else 0.0})
    tem_chat = len(tmsg) > 0
    s_audio, s_texto = escala(f_audio), escala(f_texto)
    s_chat = escala(f_chat) if tem_chat else np.zeros(len(ini))
    w = cfg["pesos_com_chat"] if tem_chat else cfg["pesos_sem_chat"]
    nota = 100 * (w.get("audio", 0) * s_audio + w.get("texto", 0) * s_texto + w.get("chat", 0) * s_chat)
    return ini, nota, s_audio, s_texto, s_chat, detalhe, tem_chat

def motivo(i, s_audio, s_texto, s_chat, det, tem_chat, estouro_db):
    partes = []
    if tem_chat and s_chat[i] >= 0.5:
        partes.append(f"chat acelerou ({det['msgs']} msgs na janela)")
    if s_audio[i] >= 0.5:
        partes.append(f"pico de volume/risada (+{estouro_db:.0f} dB acima da base)")
    if det["gatilhos"]:
        uniq = list(dict.fromkeys(det["gatilhos"]))[:5]
        partes.append("reações na fala: " + ", ".join(f"'{g}'" for g in uniq))
    elif s_texto[i] >= 0.5:
        partes.append("fala intensa/animada")
    return "; ".join(partes) or "sinal fraco (combinação leve de áudio e fala)"

def seleciona(ini, nota, s_audio, s_texto, s_chat, detalhe, tem_chat, estouro, offset, cfg, segmentos, dur):
    jan, top = cfg["janela_s"], cfg["top_n"]
    ordem = np.argsort(-nota)
    escolhidos, res = [], []
    for i in ordem:
        a = ini[i]
        if any(abs(a - ini[j]) < jan for j in escolhidos):  # sem sobreposição
            continue
        escolhidos.append(i)
        ini_s, fim_s = float(a), float(a + jan)
        # ajusta aos limites de frase da transcrição (até 8 s) mantendo 20-45 s
        for s in segmentos:
            if s["inicio"] <= ini_s < s["fim"] and ini_s - s["inicio"] <= 8:
                ini_s = s["inicio"]
            if s["inicio"] < fim_s <= s["fim"] and s["fim"] - fim_s <= 8:
                fim_s = s["fim"]
        fim_s = min(fim_s, ini_s + 45, dur)
        if fim_s - ini_s < 20:
            fim_s = min(ini_s + 20, dur)
        sl = estouro[int(a): int(a + jan)]
        res.append({
            "inicio_s": round(ini_s + offset, 2), "fim_s": round(fim_s + offset, 2),
            "duracao_s": round(fim_s - ini_s, 2), "nota": round(float(nota[i]), 1),
            "motivo": motivo(i, s_audio, s_texto, s_chat, detalhe[i], tem_chat, float(sl.max()) if len(sl) else 0.0),
            "sinais": {"audio": round(float(s_audio[i]), 2), "texto": round(float(s_texto[i]), 2),
                       "chat": round(float(s_chat[i]), 2), "msgs_chat": detalhe[i]["msgs"]},
            "trecho_falado": " ".join(s["texto"] for s in segmentos if s["fim"] > ini_s and s["inicio"] < fim_s)[:500],
        })
        if len(res) >= top:
            break
    return sorted(res, key=lambda r: -r["nota"])

def hms(s):
    s = int(s); return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--offset", type=float, default=0, help="segundo do VOD em que o arquivo começa")
    ap.add_argument("--chat", default=None, help="chat.json (opcional)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--saida", default="picos.json")
    ap.add_argument("--transcricao", default=None, help="reaproveita transcricao.json")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))["picos"]
    x = le_audio(a.video)
    dur = len(x) / SR
    _, estouro = serie_volume(x)
    if a.transcricao:
        segmentos = json.load(open(a.transcricao, encoding="utf-8"))
    else:
        segmentos = transcreve(x, cfg["whisper_modelo"])
        json.dump(segmentos, open("transcricao.json", "w", encoding="utf-8"), ensure_ascii=False)
    msgs = []
    if a.chat:
        c = json.load(open(a.chat, encoding="utf-8"))
        msgs = c.get("mensagens", []) if c.get("ok") else []
    gat = compila_gatilhos(cfg["palavras_gatilho"])
    ini, nota, sa, st, sc, det, tem_chat = pontua(a.offset, dur, estouro, msgs, segmentos, gat, cfg)
    top = seleciona(ini, nota, sa, st, sc, det, tem_chat, estouro, a.offset, cfg, segmentos, dur)
    for r in top:
        r["inicio_hms"], r["fim_hms"] = hms(r["inicio_s"]), hms(r["fim_s"])
    saida = {"video": a.video, "offset_s": a.offset, "duracao_analisada_s": round(dur, 1),
             "chat_usado": tem_chat, "mensagens_chat": len(msgs), "segmentos_transcritos": len(segmentos),
             "top": top}
    json.dump(saida, open(a.saida, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{len(top)} picos; chat_usado={tem_chat}")
    for r in top:
        print(f"{r['inicio_hms']}-{r['fim_hms']}  nota {r['nota']:5.1f}  {r['motivo']}")

if __name__ == "__main__":
    main()
