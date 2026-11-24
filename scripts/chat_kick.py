#!/usr/bin/env python3
"""Tenta baixar o chat de um VOD da Kick (API pública usada pelo player). Melhor esforço:
se falhar, grava o diagnóstico e o pipeline segue só com áudio + transcrição.
Saída: chat.json = {"ok": bool, "mensagens": [{"t": seg_desde_inicio_do_vod, "texto": str}], "diag": {...}}"""
import argparse, json, random, re, sys, datetime, time

def iso(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

def parse_ts(s):
    s = s.replace("Z", "+00:00")
    try:
        return datetime.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc).timestamp()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--vod-timestamp", type=float, required=True)
    ap.add_argument("--inicio", type=float, default=0)
    ap.add_argument("--duracao", type=float, required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    time.sleep(random.uniform(0, 25))   # espalha os blocos paralelos para não estourar o limite de taxa
    diag, msgs, ok = {"passos": []}, [], False
    try:
        from curl_cffi import requests as rq
        sess = rq.Session(impersonate="chrome")
    except Exception as e:  # sem curl_cffi
        import requests as rq
        sess = rq.Session()
        diag["aviso"] = f"curl_cffi indisponível: {e}"

    def get(url, **kw):
        """GET com retentativas (limite de taxa/429/5xx são comuns quando vários blocos consultam juntos)."""
        r = None
        for tent in range(6):
            try:
                r = sess.get(url, timeout=30, headers={"Accept": "application/json"}, **kw)
                if len(diag["passos"]) < 12 or r.status_code != 200:
                    diag["passos"].append({"url": url, "status": r.status_code, "trecho": r.text[:120], "tent": tent})
                if r.status_code == 200:
                    return r
                if r.status_code in (403, 408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 524):
                    time.sleep(min(2 ** tent, 20) + random.random() * 2)
                    continue
                return r
            except Exception as e:
                diag["passos"].append({"url": url, "erro": str(e)[:160], "tent": tent})
                time.sleep(min(2 ** tent, 20))
        return r

    r = get(f"https://kick.com/api/v2/channels/{a.slug}")
    ids = []
    if r is not None and r.status_code == 200:
        try:
            j = r.json()
            ids = [str(x) for x in (j.get("id"), (j.get("chatroom") or {}).get("id")) if x]
        except Exception as e:
            diag["erro_json"] = str(e)
    diag["ids_testados"] = ids
    t0 = a.vod_timestamp + a.inicio
    t1 = t0 + a.duracao
    for cid in ids:
        base = f"https://kick.com/api/v2/channels/{cid}/messages?start_time="
        cursor_t, paginas, coletadas, vistos = t0, 0, [], set()
        falhas, vazias = 0, 0
        while cursor_t < t1 and paginas < 1500:
            r = get(base + iso(cursor_t))
            paginas += 1
            if r is None or r.status_code != 200:
                falhas += 1
                if falhas >= 4:
                    break
                cursor_t += 30          # pula um pedaço e tenta de novo
                continue
            try:
                ms = (r.json().get("data") or {}).get("messages") or []
            except Exception:
                falhas += 1
                if falhas >= 4:
                    break
                cursor_t += 30
                continue
            novas, ultimo_ts = 0, None
            for m in ms:
                try:
                    ts = parse_ts(m["created_at"])
                except Exception:
                    continue
                ultimo_ts = ts if ultimo_ts is None else max(ultimo_ts, ts)
                if m.get("id") in vistos:
                    continue
                vistos.add(m.get("id"))
                novas += 1
                coletadas.append({"t": round(ts - a.vod_timestamp, 2), "texto": (m.get("content") or "")[:200]})
            if novas and ultimo_ts is not None:
                vazias = 0
                cursor_t = max(ultimo_ts + 0.001, cursor_t + 0.001)
            else:
                vazias += 1             # página vazia/repetida: chat calmo ou fim do histórico
                if vazias >= 40:
                    break
                cursor_t += 20 if not ms else 5
            time.sleep(0.2)
        diag[f"paginas_id_{cid}"] = paginas
        if coletadas:
            msgs = [m for m in coletadas if a.inicio <= m["t"] <= a.inicio + a.duracao]
            ok = len(msgs) > 0
            break
    diag["mensagens_no_trecho"] = len(msgs)
    ts = sorted(m["t"] for m in msgs)
    if ts:
        hist = {}
        for t in ts:
            hist[int(t // 60)] = hist.get(int(t // 60), 0) + 1
        diag["t_min_max"] = [ts[0], ts[-1]]
        diag["msgs_por_minuto"] = dict(sorted(hist.items()))
        print("chat t_min/max:", ts[0], ts[-1], "| msgs por minuto:", dict(sorted(hist.items())))
    for p in diag["passos"][:12]:
        print("chat passo:", p.get("status"), p.get("url", "")[:140], "|", (p.get("trecho") or p.get("erro") or "")[:120].replace("\n", " "))
    json.dump({"ok": ok, "mensagens": msgs, "diag": diag}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"chat: ok={ok} mensagens={len(msgs)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
