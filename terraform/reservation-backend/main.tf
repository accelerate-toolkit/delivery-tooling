terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = ">= 6.0, < 7.0" }
  }
}

variable "table_name" {
  type        = string
  description = "Shared reservation table; consumers coordinate by environment/product key."
}

variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_dynamodb_table" "reservations" {
  name                        = var.table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "scope"
  deletion_protection_enabled = true
  attribute {
    name = "scope"
    type = "S"
  }
  point_in_time_recovery { enabled = true }
  server_side_encryption { enabled = true }
  # No TTL: expiry must never delete an unresolved reservation and admit a writer.
  tags = var.tags
  lifecycle { prevent_destroy = true }
}

output "table_name" { value = aws_dynamodb_table.reservations.name }
output "table_arn" { value = aws_dynamodb_table.reservations.arn }
