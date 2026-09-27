SELECT 
    v.*,
    v.Identificacion AS strIdentificacion
FROM Operaciones.dbo.ConsultaIntegral360 v
WHERE
    Operaciones.$partition.pf_mes(v.dtmFechaInsercion) = Operaciones.$partition.pf_mes(:periodo_foto)
    AND Identificacion IN ({IDS})