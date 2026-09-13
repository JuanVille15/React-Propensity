WITH INACTIVOS_MES_ANTERIOR AS (
	SELECT  
		fct.stridentificacion AS [ID], 
		fct.strcodestadoclientefuente, 
		dime.strDescEstadoFuente 
	FROM BodegaCorporativa.[bodega].[factasociatividad] fct 
	INNER JOIN BodegaCorporativa.bodega.dimestado dime
	ON 
		fct.skEstadoCliente = dime.skEstado
		AND dime.numCodTipoEstado = 1
		AND dime.strFuente ='CooTaylor'
		AND dime.strDescEstadoFuente ='Inactivo'
	WHERE
		BodegaCorporativa.$partition.Pf_mes(fct.dtmfechainsercion) =  BodegaCorporativa.$partition.pf_mes('2026-07-01')
		AND fct.[indregistroactual] = 1 
		AND fct.strfuente = 'CooTaylor'
)
SELECT
	FORMAT(fct.dtmFechaInsercion, 'yyyyMM') AS [strPeriodo],
	fct.stridentificacion AS [strIdentificacion], 
	ma.strcodestadoclientefuente AS [strEstadoInicial], 
	CASE 
		WHEN ma.strDescEstadoFuente = 'Inactivo' 
		AND fct.strcodestadoclientefuente IN (10,11,17) THEN 1
		ELSE
			0
	END AS 'IndicadorReactivado'
FROM BodegaCorporativa.[bodega].[factasociatividad] fct
LEFT JOIN INACTIVOS_MES_ANTERIOR ma
ON
	fct.stridentificacion = ma.ID
INNER JOIN BodegaCorporativa.bodega.dimestado dime
ON 
	fct.skEstadoCliente = dime.skEstado
	AND dime.numCodTipoEstado = 1
	AND dime.strFuente ='CooTaylor'
WHERE
	BodegaCorporativa.$partition.Pf_mes(fct.dtmfechainsercion) =  BodegaCorporativa.$partition.pf_mes('2026-08-01')
	AND fct.[indregistroactual] = 1 
	AND fct.strfuente = 'CooTaylor'
	AND ma.strcodestadoclientefuente = 14;