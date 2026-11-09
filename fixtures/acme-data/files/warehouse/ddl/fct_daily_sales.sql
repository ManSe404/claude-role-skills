-- Daily sales per store and product, for the Power BI dataset.
CREATE TABLE [dw].[fct_daily_sales] (
    [daily_sales_id] BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
    [sale_date] DATE NOT NULL,
    [store_id] INT NOT NULL,
    [product_id] INT NOT NULL,
    [quantity] INT NOT NULL,
    [net_amount] FLOAT NOT NULL,
    [loaded_at] DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
