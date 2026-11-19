#!/usr/bin/env python3
"""GATE de permissão: lê streamers.yaml e só libera streamer 'aprovado'.
Autorização é decisão do Gabriel; este script nunca aprova nada sozinho.
Códigos de saída: 0 liberado | 2 não aprovado | 3 streamer não cadastrado | 4 VOD fora do período."""
import argparse, json, sys, datetime
import yaml

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--streamers", default="streamers.yaml")
    ap.add_argument("--id", required=True)
    ap.add_argument("--vod-timestamp", type=float, default=None, help="epoch do início do VOD (UTC)")
    a = ap.parse_args()
    dados = yaml.safe_load(open(a.streamers, encoding="utf-8")) or {}
    st = (dados.get("streamers") or {}).get(a.id)
    if not st:
        print(f"::error::Streamer '{a.id}' NÃO está em streamers.yaml. Peça ao Claude o RELATÓRIO de evidências "
              "(bio/Discord/campanhas públicas) e decida; o pipeline não aprova sozinho.")
        return 3
    status = st.get("status_permissao")
    if status != "aprovado":
        print(f"::error::Streamer '{st.get('nome', a.id)}' está com status_permissao='{status}'. "
              "Só 'aprovado' libera o pipeline. Fonte registrada: " + str(st.get("fonte_da_permissao")))
        return 2
    regras = st.get("regras_da_campanha") or {}
    minimo = regras.get("conteudo_a_partir_de")
    if minimo and a.vod_timestamp:
        dt = datetime.datetime.fromtimestamp(a.vod_timestamp, datetime.timezone.utc).date()
        if dt < datetime.date.fromisoformat(str(minimo)):
            print(f"::error::VOD de {dt} é anterior ao início permitido da campanha ({minimo}).")
            return 4
    print(f"GATE OK: {st.get('nome')} aprovado. Fonte: {' '.join(str(st.get('fonte_da_permissao')).split())}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
