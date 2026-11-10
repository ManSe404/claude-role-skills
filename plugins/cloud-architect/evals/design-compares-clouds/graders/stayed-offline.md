---
type: regex
pattern: 'cloud_prices\.py[^\n]*--online|curl |wget '
match: not_contains
target: trace
---
