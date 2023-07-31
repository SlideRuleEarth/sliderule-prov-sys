# ALB Security Group (Traffic Internet -> web ALB)
resource "aws_security_group" "ps-web-load-balancer" {
  name        = "${var.domain_root}-ps-web-lb-sg"
  description = "Controls access to the web ALB"
  vpc_id      = aws_vpc.prov-sys-vpc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "${var.domain_root}-ps-web-lb-sg"
  }
}

# ECS Security group (traffic web ALB -> ECS, ssh -> ECS)
resource "aws_security_group" "ecs-ps-web" {
  name        = "${var.domain_root}-ps-ecs-web-sg"
  description = "Allows inbound access from the web ALB only"
  vpc_id      = aws_vpc.prov-sys-vpc.id

  ingress {
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.ps-web-load-balancer.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "${var.domain_root}-ps-ecs-web-sg"
  }
}
# RDS Security Group (traffic web ECS -> RDS)
resource "aws_security_group" "rds" {
  name        = "${var.domain_root}-ps-rds-sg"
  description = "Allows inbound access from web ECS only"
  vpc_id      = aws_vpc.prov-sys-vpc.id

  ingress {
    protocol        = "tcp"
    from_port       = "5432"
    to_port         = "5432"
    security_groups = [aws_security_group.ecs-ps-web.id]
  }

  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "${var.domain_root}-ps-rds-sg"
  }
}
