resource "random_id" "suffix" {
  byte_length = 3
}

resource "aws_db_subnet_group" "main" {
  name       = "${local.prefix}-db"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

resource "aws_db_instance" "main" {
  identifier                      = "stagefront-tickets-prod"
  engine                          = "postgres"
  engine_version                  = "17.6"
  instance_class                  = "db.m6i.large"
  allocated_storage               = 100
  storage_type                    = "gp3"
  storage_encrypted               = true
  username                        = "app"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.db.id]
  publicly_accessible             = true
  multi_az                        = false
  backup_retention_period         = 7
  deletion_protection             = true
  enabled_cloudwatch_logs_exports = ["postgresql"]
  tags                            = local.tags
}

resource "aws_secretsmanager_secret" "db" {
  name = "stagefront/prod/db"
  tags = local.tags
}

resource "aws_s3_bucket" "tickets" {
  bucket = "stagefront-tickets-${random_id.suffix.hex}"
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "tickets" {
  bucket                  = aws_s3_bucket.tickets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "tickets" {
  bucket = aws_s3_bucket.tickets.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "tickets" {
  bucket = aws_s3_bucket.tickets.id

  rule {
    id     = "archive"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_s3_bucket" "backups" {
  bucket = "stagefront-backups-prod"
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket                  = aws_s3_bucket.backups.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
