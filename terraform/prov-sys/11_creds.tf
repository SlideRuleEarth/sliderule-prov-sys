# Decode from json
data "aws_secretsmanager_secret_version" "creds" {
  secret_id = "${var.domain}/secrets"
}
locals {
  provsys_creds = jsondecode(
    data.aws_secretsmanager_secret_version.creds.secret_string
  )
}
