---
type: regex
pattern: '\baws (sts|ec2|s3|rds|cloudformation|configure|login|resourcegroupstaggingapi|configservice)\b'
match: not_contains
target: trace
---
