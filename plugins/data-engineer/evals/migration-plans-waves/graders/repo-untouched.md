---
type: regex
pattern: "fix_stock_snapshot,jobs/fix_stock_snapshot\\.sql,0 3 \\* \\* \\*"
target: {source: file, path: acme-pipeline/legacy/inventory.csv}
---
