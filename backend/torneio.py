"""
Regras do torneio de fim de ano (4 times, cores fixas).

1ª fase: jogo único entre todos, na ordem da tabela oficial.
2ª fase: 3º x 4º (disputa de terceiro lugar) e 1º x 2º (final).

Critérios de desempate da 1ª fase (após pontos):
  i.   Confronto direto — com 3+ empatados, mini-tabela entre eles
       (pontos, saldo, gols marcados apenas nos jogos entre os empatados)
  ii.  Saldo de gols geral
  iii. Gols marcados geral
  iv.  Sorteio — feito no campo e informado manualmente no app
"""

CORES_TORNEIO = ("Branco", "Verde", "Laranja", "Azul")

# Jogos 01 a 06 da tabela oficial (por cor do time)
TABELA_GRUPOS = [
    ("Branco", "Verde"),
    ("Laranja", "Azul"),
    ("Verde", "Laranja"),
    ("Azul", "Branco"),
    ("Verde", "Azul"),
    ("Branco", "Laranja"),
]

ORDEM_TERCEIRO = 7
ORDEM_FINAL = 8
FASES_MATA_MATA = ("terceiro", "final")
TEMPO_PADRAO_MINUTOS = 16


def eh_grupos(jogo) -> bool:
    return jogo.fase in (None, "grupos")


def eh_mata_mata(jogo) -> bool:
    return jogo.fase in FASES_MATA_MATA


def vencedor(jogo):
    """time_id vencedor (considera pênaltis) ou None se empate/sem definição."""
    if jogo.gols_time_a > jogo.gols_time_b:
        return jogo.time_a_id
    if jogo.gols_time_b > jogo.gols_time_a:
        return jogo.time_b_id
    if jogo.penaltis_a is not None and jogo.penaltis_b is not None:
        if jogo.penaltis_a > jogo.penaltis_b:
            return jogo.time_a_id
        if jogo.penaltis_b > jogo.penaltis_a:
            return jogo.time_b_id
    return None


def perdedor(jogo):
    v = vencedor(jogo)
    if v is None:
        return None
    return jogo.time_b_id if v == jogo.time_a_id else jogo.time_a_id


def _estatisticas(time_ids, jogos):
    """Pontos/saldo/gols considerando apenas jogos finalizados entre os time_ids."""
    ids = set(time_ids)
    st = {
        t: {"pontos": 0, "vitorias": 0, "empates": 0, "derrotas": 0,
            "gols_pro": 0, "gols_contra": 0}
        for t in time_ids
    }
    for j in jogos:
        if j.status != "finalizado" or not eh_grupos(j):
            continue
        if j.time_a_id not in ids or j.time_b_id not in ids:
            continue
        a, b = st[j.time_a_id], st[j.time_b_id]
        a["gols_pro"] += j.gols_time_a
        a["gols_contra"] += j.gols_time_b
        b["gols_pro"] += j.gols_time_b
        b["gols_contra"] += j.gols_time_a
        if j.gols_time_a > j.gols_time_b:
            a["pontos"] += 3; a["vitorias"] += 1; b["derrotas"] += 1
        elif j.gols_time_b > j.gols_time_a:
            b["pontos"] += 3; b["vitorias"] += 1; a["derrotas"] += 1
        else:
            a["pontos"] += 1; b["pontos"] += 1
            a["empates"] += 1; b["empates"] += 1
    return st


def _agrupar(ids, chave):
    """Ordena desc por chave e agrupa ids com chave igual em blocos."""
    ordenados = sorted(ids, key=chave, reverse=True)
    blocos = []
    for t in ordenados:
        if blocos and chave(blocos[-1][0]) == chave(t):
            blocos[-1].append(t)
        else:
            blocos.append([t])
    return blocos


def classificar_grupos(times, jogos):
    """
    times: lista de objetos com id, nome, cor
    jogos: lista de Jogo da pelada

    Retorna dict:
      tabela             → linhas ordenadas (com posicao e stats gerais)
      sorteio_necessario → True se há empate total na fronteira 2º/3º lugar
      empatados          → time_ids empatados nessa fronteira
      vagas_final        → quantas vagas da final estão em disputa entre eles
    """
    ids = [t.id for t in times]
    geral = _estatisticas(ids, jogos)

    def saldo(t):
        return geral[t]["gols_pro"] - geral[t]["gols_contra"]

    def ordenar(grupo):
        """Retorna lista de blocos ordenados; bloco com >1 time = empate não resolvido."""
        if len(grupo) == 1:
            return [grupo]

        # i. Confronto direto / mini-tabela entre os empatados
        h2h = _estatisticas(grupo, jogos)
        blocos = _agrupar(grupo, lambda t: (
            h2h[t]["pontos"],
            h2h[t]["gols_pro"] - h2h[t]["gols_contra"],
            h2h[t]["gols_pro"],
        ))
        if len(blocos) > 1:
            return [b for bloco in blocos for b in ordenar(bloco)]

        # ii/iii. Saldo de gols geral, gols marcados geral
        blocos = _agrupar(grupo, lambda t: (saldo(t), geral[t]["gols_pro"]))
        if len(blocos) > 1:
            return [b for bloco in blocos for b in ordenar(bloco)]

        # iv. Sorteio
        return [grupo]

    blocos = []
    for grupo_pontos in _agrupar(ids, lambda t: geral[t]["pontos"]):
        blocos.extend(ordenar(grupo_pontos))

    times_por_id = {t.id: t for t in times}
    tabela = []
    sorteio_necessario = False
    empatados = []
    vagas_final = 0

    pos = 0
    for bloco in blocos:
        inicio = pos
        fim = pos + len(bloco)
        if len(bloco) > 1 and inicio < 2 < fim:
            sorteio_necessario = True
            empatados = list(bloco)
            vagas_final = 2 - inicio
        for t in sorted(bloco, key=lambda x: times_por_id[x].nome):
            pos += 1
            time = times_por_id[t]
            tabela.append({
                "time_id": t,
                "nome": time.nome,
                "cor": time.cor,
                "posicao": pos,
                "empate_sorteio": len(bloco) > 1,
                **geral[t],
            })

    return {
        "tabela": tabela,
        "sorteio_necessario": sorteio_necessario,
        "empatados": empatados,
        "vagas_final": vagas_final,
    }


def classificacao_final(jogos):
    """Lista de time_ids [1º, 2º, 3º, 4º] — posições ainda indefinidas ficam None."""
    final = next((j for j in jogos if j.fase == "final"), None)
    terceiro = next((j for j in jogos if j.fase == "terceiro"), None)

    def resultado(j):
        if j is None or j.status != "finalizado":
            return None, None
        return vencedor(j), perdedor(j)

    campeao, vice = resultado(final)
    terc, quarto = resultado(terceiro)
    return [campeao, vice, terc, quarto]
