SELECT
	strPeriodo as [strPeriodo],
	strIdentificacion as [strIdentificacion],
	COUNT(DISTINCT(strAgrupacion)) as [Numcantidadproductos]
FROM BodegaCorporativa.bodega.factTenenciaProductos t
INNER JOIN BodegaCorporativa.bodega.lkpAnalisisProducto p
ON 
	t.nkDetalleProducto = p.nkDetalleProducto
WHERE 
	BodegaCorporativa.$partition.pf_mes(dtmFechaInsercion) =  BodegaCorporativa.$partition.pf_mes(:periodo_foto)
	AND strIdentificacion IN ({IDS})
	AND indTenencia = 1
	AND strAgrupacion IS NOT NULL
GROUP BY
	strPeriodo,strIdentificacion;