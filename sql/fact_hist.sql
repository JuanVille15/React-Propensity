SELECT
	strPeriodo as Periodo,
	strIdentificacion as Id,
	SUM(numValorVencido) as Valor_Vencido,
	SUM(numValorTotalCalculado) as Valor_Cuota_Mes
FROM BodegaCorporativa.bodega.factFacturaEstadoCuentaGECC f
INNER JOIN BodegaCorporativa.bodega.dimConceptoFacturaGECC c
ON f.strCodConcepto = c.strCodConcepto
WHERE 
	BodegaCorporativa.$partition.pf_mes(f.dtmFechaInsercion) = BodegaCorporativa.$partition.pf_mes('?')
	AND f.strIdentificacion IN ({ids})
GROUP BY strPeriodo, strIdentificacion;