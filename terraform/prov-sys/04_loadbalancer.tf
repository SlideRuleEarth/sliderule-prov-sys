# ps-web Load Balancer
resource "aws_lb" "ps-web" {
  name               = "${var.domain_root}-ps-web-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.ps-web-load-balancer.id]
  subnets            = [aws_subnet.public-subnet-1.id, aws_subnet.public-subnet-2.id]
  # access_logs {
  #  bucket = "sliderule"
  #  prefix = "access_logs/${domain}/ps-web"
  #  enabled = true
  # } 
  tags = {
    Name = "${var.domain_root}-ps-web-alb"
  }
}

# Target group
resource "aws_alb_target_group" "ps-web-target-group" {
  name     = "${var.domain_root}-ps-web-alb-tg"
  port     = 80
  protocol = "HTTP"
  vpc_id   = aws_vpc.prov-sys-vpc.id
  target_type = "ip"

  health_check {
    path                = var.ps_web_health_check_path
    port                = "traffic-port"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    timeout             = 10
    interval            = 30
    matcher             = "200"
  }
  tags = {
    Name = "${var.domain_root}-ps-web-alb-tg"
  }
}
data "aws_acm_certificate" "sliderule_cluster_cert" {
  domain      = "*.${var.domain}"
  types       = ["AMAZON_ISSUED"]
  most_recent = true
}
# Listener (redirects traffic from the load balancer to the target group)
resource "aws_alb_listener" "ps-web-https-listener" {
  load_balancer_arn = aws_lb.ps-web.id
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-2016-08"
  certificate_arn   = data.aws_acm_certificate.sliderule_cluster_cert.arn
  depends_on        = [aws_alb_target_group.ps-web-target-group]

  default_action {
    type             = "forward"
    target_group_arn = aws_alb_target_group.ps-web-target-group.arn
  }
  tags = {
    Name = "${var.domain_root}-ps-web-https-l"
  }
}
resource "aws_alb_listener" "ps-web-http-listener" {
  load_balancer_arn = aws_lb.ps-web.id
  port              = 80
  protocol          = "HTTP"  
  default_action {
    type             = "redirect"
    redirect {   
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
  tags = {
    Name = "${var.domain_root}-ps-http-l"
  }
}

data "aws_route53_zone" "selected" {
  name         = "${var.domain}"
}

resource "aws_route53_record" "ps-web-site" {
  zone_id = data.aws_route53_zone.selected.zone_id
  name    = "ps.${data.aws_route53_zone.selected.name}"
  type    = "A"
  allow_overwrite = true
  alias {
    name                   = aws_lb.ps-web.dns_name
    zone_id                = aws_lb.ps-web.zone_id
    evaluate_target_health = false
  }
}
