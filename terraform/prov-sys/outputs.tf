output "prov-sys-hostname" {
  value = aws_lb.ps-web.dns_name
}

output "final_db_snapshot_name" {
  value = aws_db_instance.prov-sys.final_snapshot_identifier
}