-- Sales of one region for the store managers. Runs on request, with the region name from the request form.
CREATE OR ALTER PROCEDURE [dw].[export_by_region]
    @region NVARCHAR(60)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @sql NVARCHAR(MAX);

    SET @sql = N'SELECT f.sale_date, st.store_name, SUM(f.net_amount) AS net_amount FROM [dw].[fct_daily_sales] AS f JOIN [marts].[dim_store] AS st ON st.store_id = f.store_id WHERE st.region = ''' + @region + N''' GROUP BY f.sale_date, st.store_name;';

    EXEC(@sql);
END;
