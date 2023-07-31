resource "aws_cloudwatch_log_group" "django-log-group" {
  name              = "/${var.domain_root}-ps/web-ecs"
  retention_in_days = var.log_retention_in_days
  tags = {
    Name = "${var.domain_root}-ps-WebLgGrp"
  }
}

resource "aws_cloudwatch_log_stream" "django-log-stream" {
  name           = "${var.domain_root}-ps-WebLgStrm"
  log_group_name = aws_cloudwatch_log_group.django-log-group.name
}

resource "aws_cloudwatch_log_group" "nginx-log-group" {
  name              = "/${var.domain_root}-ps/nginx-ecs"
  retention_in_days = var.log_retention_in_days
  tags = {
    Name = "${var.domain_root}-ps-NGNXLgGrp"
  }
}

resource "aws_cloudwatch_log_stream" "nginx-log-stream" {
  name           = "${var.domain_root}-ps-WebLgStrm"
  log_group_name = aws_cloudwatch_log_group.nginx-log-group.name
}

resource "aws_cloudwatch_log_group" "ps-server-log-group" {
  name              = "/${var.domain_root}-ps/svr-ecs"
  retention_in_days = var.log_retention_in_days
  tags = {
    Name = "${var.domain_root}-ps-SvrLgGrp"
  }
}

resource "aws_cloudwatch_log_stream" "ps-server-log-stream" {
  name           = "${var.domain_root}-ps-SvrLgStrm"
  log_group_name = aws_cloudwatch_log_group.ps-server-log-group.name
}

