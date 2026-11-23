-- =====================================================================
-- Zera os JOGOS de uma pelada, mantendo a pelada, as presenças e os times
-- (com seus atletas). Depois do reset, os jogos podem ser gerados de novo
-- pelo app (aba Jogos → Gerar Jogos), como se nada tivesse sido jogado.
--
-- Caso de uso: testar o torneio definitivo (jogos, 2ª fase, pênaltis, card)
-- e depois limpar o teste sem perder a formação dos times.
--
-- APAGA:    gols/assistências, partidas, jogos (incluindo 3º lugar e final)
-- MANTÉM:   pelada, presenças, times e atletas de cada time
-- RESETA:   status da pelada → 'planejada', campeão → vazio
--
-- COMO USAR
--   1. Troque o número em  >>> ID DA PELADA <<<  abaixo.
--      (para achar o ID: abra https://peladatop-app.onrender.com/peladas)
--   2. Rode o script inteiro no banco certo (sábado e quinta são bancos diferentes):
--        psql '<External Database URL>' -v ON_ERROR_STOP=1 -f resetar_jogos_pelada.sql
--      ou cole tudo no DBeaver/pgAdmin e execute como script.
--   3. Por padrão ele termina com ROLLBACK: mostra o que seria apagado e
--      desfaz tudo. Confira a saída e, para valer, troque o ROLLBACK do
--      final por COMMIT e rode de novo.
--   4. No app: feche e abra de novo (limpa o cache) e gere os jogos.
-- =====================================================================

BEGIN;

CREATE TEMP TABLE alvo ON COMMIT DROP AS
SELECT 0 AS pelada_id;   -- >>> ID DA PELADA <<<

-- ---------------------------------------------------------------------
-- Trava de segurança: aborta se a pelada não existe, ou se é uma pelada
-- normal FINALIZADA (já somou títulos aos atletas; zerar os jogos deixaria
-- os títulos inconsistentes). Torneio não soma títulos, pode ser resetado.
-- ---------------------------------------------------------------------
DO $$
DECLARE
  p pelada%ROWTYPE;
BEGIN
  SELECT * INTO p FROM pelada WHERE id = (SELECT pelada_id FROM alvo);
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Pelada % não encontrada', (SELECT pelada_id FROM alvo);
  END IF;
  IF p.status = 'finalizada' AND p.tipo <> 'torneio' THEN
    RAISE EXCEPTION 'Pelada % é uma pelada normal FINALIZADA (já somou títulos). Recusado.', p.id;
  END IF;
END $$;

-- ---------------------------------------------------------------------
-- Prévia
-- ---------------------------------------------------------------------
SELECT id, data, local, tipo, status, campeao
FROM pelada WHERE id = (SELECT pelada_id FROM alvo);

-- Times que serão MANTIDOS
SELECT t.nome AS time_mantido, COUNT(ta.id) AS atletas
FROM "time" t LEFT JOIN timeatleta ta ON ta.time_id = t.id
WHERE t.pelada_id = (SELECT pelada_id FROM alvo)
GROUP BY t.nome ORDER BY t.nome;

-- Jogos que serão APAGADOS
SELECT j.ordem, j.fase, ta.nome AS time_a, j.gols_time_a, j.gols_time_b, tb.nome AS time_b, j.status
FROM jogo j
JOIN "time" ta ON ta.id = j.time_a_id
JOIN "time" tb ON tb.id = j.time_b_id
WHERE j.pelada_id = (SELECT pelada_id FROM alvo)
ORDER BY j.ordem NULLS LAST, j.id;

-- Gols/assistências que sairão das estatísticas
WITH ev AS (
  SELECT e.* FROM eventopartida e
  JOIN partida pa ON pa.id = e.partida_id
  JOIN jogo j     ON j.id = pa.jogo_id
  WHERE j.pelada_id = (SELECT pelada_id FROM alvo)
)
SELECT a.nome,
       COUNT(*) FILTER (WHERE ev.atleta_gol_id = a.id)         AS gols_removidos,
       COUNT(*) FILTER (WHERE ev.atleta_assistencia_id = a.id) AS assist_removidas
FROM atleta a
JOIN ev ON a.id IN (ev.atleta_gol_id, ev.atleta_assistencia_id)
GROUP BY a.nome
ORDER BY gols_removidos DESC, assist_removidas DESC;

-- ---------------------------------------------------------------------
-- Reset
-- ---------------------------------------------------------------------
DELETE FROM eventopartida WHERE partida_id IN (
  SELECT pa.id FROM partida pa JOIN jogo j ON j.id = pa.jogo_id
  WHERE j.pelada_id = (SELECT pelada_id FROM alvo));

DELETE FROM partida WHERE jogo_id IN (
  SELECT id FROM jogo WHERE pelada_id = (SELECT pelada_id FROM alvo));

DELETE FROM jogo WHERE pelada_id = (SELECT pelada_id FROM alvo);

UPDATE pelada SET status = 'planejada', campeao = NULL
WHERE id = (SELECT pelada_id FROM alvo);

-- >>> Troque por COMMIT para valer <<<
ROLLBACK;
