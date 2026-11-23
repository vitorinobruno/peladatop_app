-- =====================================================================
-- Apaga DEFINITIVAMENTE uma pelada e tudo ligado a ela:
-- gols/assistências, partidas, jogos, times, atletas dos times e presenças.
-- Atletas NÃO são apagados (são compartilhados entre peladas).
--
-- Uso para peladas de teste. O soft delete do app (DELETE /peladas/{id})
-- não remove os gols das estatísticas gerais.
--
-- COMO USAR
--   1. Troque o número em  >>> ID DA PELADA <<<  abaixo.
--      (para achar o ID: abra https://peladatop-app.onrender.com/peladas)
--   2. Rode o script inteiro no banco certo (sábado e quinta são bancos diferentes):
--        psql '<External Database URL>' -v ON_ERROR_STOP=1 -f apagar_pelada.sql
--      ou cole tudo no DBeaver/pgAdmin e execute como script.
--   3. Por padrão ele termina com ROLLBACK: mostra o que seria apagado e
--      desfaz tudo. Confira a saída e, para apagar de verdade, troque o
--      ROLLBACK do final por COMMIT e rode de novo.
-- =====================================================================

BEGIN;

CREATE TEMP TABLE alvo ON COMMIT DROP AS
SELECT 0 AS pelada_id;   -- >>> ID DA PELADA <<<

-- ---------------------------------------------------------------------
-- Trava de segurança: aborta se a pelada não existe, ou se é uma pelada
-- normal FINALIZADA (já somou títulos aos atletas; apagar deixaria os
-- títulos inconsistentes). Torneio não soma títulos, pode ser apagado.
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
-- Prévia: a pelada e quem perde gols/assistências nas estatísticas
-- ---------------------------------------------------------------------
SELECT id, data, local, tipo, status, deletada
FROM pelada WHERE id = (SELECT pelada_id FROM alvo);

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
-- Exclusão (filhos antes dos pais). O psql mostra "DELETE n" em cada uma.
-- ---------------------------------------------------------------------
DELETE FROM eventopartida WHERE partida_id IN (
  SELECT pa.id FROM partida pa JOIN jogo j ON j.id = pa.jogo_id
  WHERE j.pelada_id = (SELECT pelada_id FROM alvo));

DELETE FROM partida WHERE jogo_id IN (
  SELECT id FROM jogo WHERE pelada_id = (SELECT pelada_id FROM alvo));

DELETE FROM jogo WHERE pelada_id = (SELECT pelada_id FROM alvo);

DELETE FROM timeatleta WHERE time_id IN (
  SELECT id FROM "time" WHERE pelada_id = (SELECT pelada_id FROM alvo));

DELETE FROM "time" WHERE pelada_id = (SELECT pelada_id FROM alvo);

DELETE FROM presenca WHERE pelada_id = (SELECT pelada_id FROM alvo);

DELETE FROM pelada WHERE id = (SELECT pelada_id FROM alvo);

-- >>> Troque por COMMIT para apagar de verdade <<<
ROLLBACK;
