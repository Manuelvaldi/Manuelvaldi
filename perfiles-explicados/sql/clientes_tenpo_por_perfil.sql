-- % de clientes Tenpo por perfil (P1..P7) para la lámina "Características por perfil".
--
-- Fuente: vista tenpo-sandbox.riesgo_backup.vw_clientes_ISE_BNB_edad_202607
--         (1 fila por cliente Tenpo: user_id, grupo_ISE, B_NB_Tenpo, grupo_etario; 2.598.709 filas).
-- Matriz edad x GSE x bancarización -> perfil: copiada de la lámina 2 del deck
--         ("Resultado: 7 perfiles sobre las 90 celdas"). Sub Bancarizado (SB) = 'NB' en la vista.
--
-- SUPUESTOS (revisar antes de usar):
--   * Los valores de grupo_ISE son 'E','D','C3','C2','ABC1', los de B_NB_Tenpo 'B'/'NB' y los de
--     grupo_etario '18-24' ... '60+' (así aparecen en el Excel DEBT_CUBE_g_Tenpo_reconstruido).
--   * Base = TODOS los clientes Tenpo (incluye 55+ y E SB), para que los 7 perfiles sumen el 100%
--     de clientes. Si Daría prefiere solo el universo 18-54 sin E SB, descomentar el filtro del final.
--
-- CONTROL: la columna `clientes` debe sumar 2.598.709 y no debe aparecer la fila 'SIN_MATCH'.
-- SIN TESTEAR: esta consulta se escribió sin acceso a BigQuery (el contenedor no tiene credenciales).

WITH matriz AS (
  SELECT * FROM UNNEST([
    STRUCT('18-24' AS edad, 'E' AS gse, 'NB' AS pos, 'P3' AS perfil),
    STRUCT('18-24' AS edad, 'D' AS gse, 'NB' AS pos, 'P3' AS perfil),
    STRUCT('18-24' AS edad, 'C3' AS gse, 'NB' AS pos, 'P3' AS perfil),
    STRUCT('18-24' AS edad, 'C2' AS gse, 'NB' AS pos, 'P5' AS perfil),
    STRUCT('18-24' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P5' AS perfil),
    STRUCT('18-24' AS edad, 'E' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('18-24' AS edad, 'D' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('18-24' AS edad, 'C3' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('18-24' AS edad, 'C2' AS gse, 'B' AS pos, 'P5' AS perfil),
    STRUCT('18-24' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P5' AS perfil),
    STRUCT('25-29' AS edad, 'E' AS gse, 'NB' AS pos, 'P3' AS perfil),
    STRUCT('25-29' AS edad, 'D' AS gse, 'NB' AS pos, 'P3' AS perfil),
    STRUCT('25-29' AS edad, 'C3' AS gse, 'NB' AS pos, 'P3' AS perfil),
    STRUCT('25-29' AS edad, 'C2' AS gse, 'NB' AS pos, 'P5' AS perfil),
    STRUCT('25-29' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P5' AS perfil),
    STRUCT('25-29' AS edad, 'E' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('25-29' AS edad, 'D' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('25-29' AS edad, 'C3' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('25-29' AS edad, 'C2' AS gse, 'B' AS pos, 'P5' AS perfil),
    STRUCT('25-29' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P5' AS perfil),
    STRUCT('30-34' AS edad, 'E' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('30-34' AS edad, 'D' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('30-34' AS edad, 'C3' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('30-34' AS edad, 'C2' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('30-34' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P7' AS perfil),
    STRUCT('30-34' AS edad, 'E' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('30-34' AS edad, 'D' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('30-34' AS edad, 'C3' AS gse, 'B' AS pos, 'P3' AS perfil),
    STRUCT('30-34' AS edad, 'C2' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('30-34' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('35-39' AS edad, 'E' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('35-39' AS edad, 'D' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('35-39' AS edad, 'C3' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('35-39' AS edad, 'C2' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('35-39' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P7' AS perfil),
    STRUCT('35-39' AS edad, 'E' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('35-39' AS edad, 'D' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('35-39' AS edad, 'C3' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('35-39' AS edad, 'C2' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('35-39' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('40-44' AS edad, 'E' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('40-44' AS edad, 'D' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('40-44' AS edad, 'C3' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('40-44' AS edad, 'C2' AS gse, 'NB' AS pos, 'P2' AS perfil),
    STRUCT('40-44' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P7' AS perfil),
    STRUCT('40-44' AS edad, 'E' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('40-44' AS edad, 'D' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('40-44' AS edad, 'C3' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('40-44' AS edad, 'C2' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('40-44' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('45-49' AS edad, 'E' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('45-49' AS edad, 'D' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('45-49' AS edad, 'C3' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('45-49' AS edad, 'C2' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('45-49' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P7' AS perfil),
    STRUCT('45-49' AS edad, 'E' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('45-49' AS edad, 'D' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('45-49' AS edad, 'C3' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('45-49' AS edad, 'C2' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('45-49' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('50-54' AS edad, 'E' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('50-54' AS edad, 'D' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('50-54' AS edad, 'C3' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('50-54' AS edad, 'C2' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('50-54' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P7' AS perfil),
    STRUCT('50-54' AS edad, 'E' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('50-54' AS edad, 'D' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('50-54' AS edad, 'C3' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('50-54' AS edad, 'C2' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('50-54' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('55-59' AS edad, 'E' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('55-59' AS edad, 'D' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('55-59' AS edad, 'C3' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('55-59' AS edad, 'C2' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('55-59' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P7' AS perfil),
    STRUCT('55-59' AS edad, 'E' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('55-59' AS edad, 'D' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('55-59' AS edad, 'C3' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('55-59' AS edad, 'C2' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('55-59' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('60+' AS edad, 'E' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('60+' AS edad, 'D' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('60+' AS edad, 'C3' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('60+' AS edad, 'C2' AS gse, 'NB' AS pos, 'P1' AS perfil),
    STRUCT('60+' AS edad, 'ABC1' AS gse, 'NB' AS pos, 'P7' AS perfil),
    STRUCT('60+' AS edad, 'E' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('60+' AS edad, 'D' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('60+' AS edad, 'C3' AS gse, 'B' AS pos, 'P4' AS perfil),
    STRUCT('60+' AS edad, 'C2' AS gse, 'B' AS pos, 'P6' AS perfil),
    STRUCT('60+' AS edad, 'ABC1' AS gse, 'B' AS pos, 'P6' AS perfil)
  ])
)
SELECT
  COALESCE(m.perfil, 'SIN_MATCH')                                   AS perfil,
  COUNT(*)                                                          AS clientes,
  ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)                  AS pct_clientes_tenpo
FROM `tenpo-sandbox.riesgo_backup.vw_clientes_ISE_BNB_edad_202607` v
LEFT JOIN matriz m
  ON  v.grupo_etario = m.edad
  AND v.grupo_ISE    = m.gse
  AND v.B_NB_Tenpo   = m.pos
-- Alternativa: solo universo Tenpo (18-54, sin E Sub Bancarizado)
-- WHERE v.grupo_etario IN ('18-24','25-29','30-34','35-39','40-44','45-49','50-54')
--   AND NOT (v.grupo_ISE = 'E' AND v.B_NB_Tenpo = 'NB')
GROUP BY 1
ORDER BY 1;
