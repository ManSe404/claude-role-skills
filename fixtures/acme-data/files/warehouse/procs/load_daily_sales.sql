-- Adds one day to dw.fct_daily_sales. The nightly job calls it with yesterday's date.
CREATE OR ALTER PROCEDURE [dw].[load_daily_sales]
    @load_date DATE
AS
BEGIN
    SET NOCOUNT ON;

    WITH daily AS (
        SELECT
            sale_date,
            store_id,
            product_id,
            SUM(quantity) AS quantity,
            SUM(net_amount) AS net_amount
        FROM [marts].[fct_sales] WITH (NOLOCK)
        /* JOIN retired_table */
        GROUP BY sale_date, store_id, product_id
    )
    INSERT INTO [dw].[fct_daily_sales] ([sale_date], [store_id], [product_id], [quantity], [net_amount])
    SELECT sale_date, store_id, product_id, quantity, net_amount
    FROM daily
    WHERE sale_date = @load_date;
END;
