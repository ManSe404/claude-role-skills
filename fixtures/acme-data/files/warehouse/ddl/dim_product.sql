-- The product list as the warehouse keeps it.
CREATE TABLE [dw].[dim_product] (
    [product_id] INT NOT NULL,
    [name] NVARCHAR(120) NOT NULL,
    [category] NVARCHAR(60) NOT NULL,
    [list_price] DECIMAL(10, 2) NOT NULL,
    [updated_at] DATETIME2 NOT NULL,
    CONSTRAINT [pk_dim_product] PRIMARY KEY ([product_id])
);
