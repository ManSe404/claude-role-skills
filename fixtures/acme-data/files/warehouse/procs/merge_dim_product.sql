-- Keeps dw.dim_product in step with the ERP product list. Runs every night after dbt.
CREATE OR ALTER PROCEDURE [dw].[merge_dim_product]
AS
BEGIN
    SET NOCOUNT ON;

    MERGE [dw].[dim_product] AS t
    USING [staging].[stg_products] AS s WITH (NOLOCK)
        ON t.product_id = s.product_id
    WHEN MATCHED THEN UPDATE SET
        t.name = s.name,
        t.category = s.category,
        t.list_price = s.list_price,
        t.updated_at = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT ([product_id], [name], [category], [list_price], [updated_at])
        VALUES (s.product_id, s.name, s.category, s.list_price, SYSUTCDATETIME());
END;
