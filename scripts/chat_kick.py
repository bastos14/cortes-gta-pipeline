#!/usr/bin/env python3
"""Tenta baixar o chat de um VOD da Kick (API pública usada pelo player). Melhor esforço:
se falhar, grava o diagnóstico e o pipeline segue só com áudio + transcrição.
Saída: chat.json = {"ok": bool, "mensagens": [{"t": seg_desde_inicio_do_vod, "texto": str}], "diag": {...}}"""
import argparse, json, re, sys, datetime, time

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
    diag, msgs, ok = {"passos": []}, [], False
    try:
        from curl_cffi import requests as rq
        sess = rq.Session(impersonate="chrome")
    except Exception as e:  # sem curl_cffi
        import requests as rq
        sess = rq.Session()
        diag["aviso"] = f"curl_cffi indisponível: {e}"

    def get(url, **kw):
        try:
            r = sess.get(url, timeout=30, headers={"Accept": "application/json"}, **kw)
            diag["passos"].append({"url": url, "status": r.status_code, "trecho": r.text[:200]})
            return r
        except Exception as e:
            diag["passos"].append({"url": url, "erro": str(e)[:200]})
            return None

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
        while cursor_t < t1 and paginas < 800:
            r = get(base + iso(cursor_t))
            paginas += 1
            if r is None or r.status_code != 200:
                break
            try:
                ms = (r.json().get("data") or {}).get("messages") or []
            except Exception:
                break
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
            if not novas or ultimo_ts is None:
                break   # nada novo: acabou ou a API repetiu a página
            cursor_t = max(ultimo_ts + 0.001, cursor_t + 0.001)
            time.sleep(0.15)
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
    for p in diag["passos"][:6]:
        print("chat passo:", p.get("status"), p.get("url", "")[:140], "|", (p.get("trecho") or p.get("erro") or "")[:120].replace("\n", " "))
    json.dump({"ok": ok, "mensagens": msgs, "diag": diag}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"chat: ok={ok} mensagens={len(msgs)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
