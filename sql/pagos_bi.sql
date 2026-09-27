SELECT
	r.strPeriodo as [Periodo],
	r.strIdentificacion as [Id],
	SUM(r.numRecaudoTotal) as [Recaudo_Total]
FROM BodegaCorporativa.bodega.factRecaudoMesConceptoGECC r
INNER JOIN BodegaCorporativa.bodega.dimConceptoFacturaGECC c
ON 
	r.strCodConcepto = c.strCodConcepto
WHERE 
	BodegaCorporativa.$partition.pf_mes(r.dtmFechaInsercion) = BodegaCorporativa.$partition.pf_mes('?')
	AND c.strEmpresaGECC = '{empresa}'
	AND r.strIdentificacion IN ({ids})
GROUP BY
	r.strPeriodo,r.strIdentificacion;