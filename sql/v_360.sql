 SELECT 
    {COLUMNAS_VALIDAS}
    FROM Operaciones.dbo.ConsultaIntegral360
WHERE
    Periodo = ?
    AND Identificacion IN ({ids})