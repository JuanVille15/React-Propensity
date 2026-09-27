SELECT
	r.strPeriodo as [strPeriodo],
	r.strIdentificacion as [strIdentificacion],
	SUM(r.numRecaudoTotal) as [Recaudo_Total]
FROM BodegaCorporativa.bodega.factRecaudoMesConceptoGECC r
INNER JOIN BodegaCorporativa.bodega.dimConceptoFacturaGECC c
ON 
	r.strCodConcepto = c.strCodConcepto
WHERE 
	BodegaCorporativa.$partition.pf_mes(r.dtmFechaInsercion) = BodegaCorporativa.$partition.pf_mes(:periodo_foto)
	AND c.strEmpresaGECC = '{empresa}'
	AND r.strIdentificacion IN ({IDS})
GROUP BY
	r.strPeriodo,r.strIdentificacion;