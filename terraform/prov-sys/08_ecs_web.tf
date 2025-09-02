resource "aws_ecs_cluster" "prov-sys" {
  name = "${var.domain_root}-ps-clstr"
  tags = {
    Name = "${var.domain_root}-ps-clstr"
  }
}

resource "aws_ecs_cluster_capacity_providers" "prov-sys" {
  cluster_name       = aws_ecs_cluster.prov-sys.name
  capacity_providers = ["FARGATE"]

  default_capacity_provider_strategy {
    base              = 1
    weight            = 100
    capacity_provider = "FARGATE"
  }
}

#########################################################
# Build container definitions as native HCL
#########################################################

data "aws_secretsmanager_secret" "provsys" {
  name = "testsliderule.org/secrets"
}

locals {
  provsys_secret_arn  = data.aws_secretsmanager_secret.provsys.arn
  ps_server_port_safe = coalesce(var.ps_server_port, 50051)

  common_log_opts = {
    "awslogs-create-group" = "true"
    "awslogs-group"        = "/ecs/${var.domain_root}-prov-sys"
    "awslogs-region"       = var.region
  }

  container_definitions = [
    {
      name            = "ps-server"
      image           = var.docker_image_url_ps-server
      essential       = true
      command         = ["python", "ps_server.py"]
      linuxParameters = { initProcessEnabled = true }
      portMappings    = [{ containerPort = tonumber(local.ps_server_port_safe), protocol = "tcp" }]
      environment = [
        { name = "PS_SERVER_PORT", value = tostring(local.ps_server_port_safe) },
        { name = "GRPC_POLL_STRATEGY", value = "poll" },
        { name = "CLUSTER_REPO", value = local.provsys_creds.cluster_repo },
        { name = "DOMAIN", value = var.domain }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options   = merge(local.common_log_opts, { "awslogs-stream-prefix" = "${var.domain_root}-ps-server" })
      }
    },

    {
      name         = "redis"
      image        = var.docker_image_url_redis
      essential    = true
      portMappings = [{ containerPort = tonumber(var.redis_port), protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options   = merge(local.common_log_opts, { "awslogs-stream-prefix" = "${var.domain_root}-ps-redis" })
      }
    },

    {
      name            = "ps-web"
      image           = var.docker_image_url_ps-web
      essential       = true
      dependsOn       = [
        { containerName = "redis",     condition = "START" },
        { containerName = "ps-server", condition = "START" }
      ]
      linuxParameters = { initProcessEnabled = true }
      portMappings    = [{ containerPort = tonumber(var.django_app_port), protocol = "tcp" }]

      environment = [
        { name = "SQL_ENGINE",           value = "django.db.backends.postgresql" },
        { name = "POSTGRES_DB",          value = local.provsys_creds.rds_db_name },
        { name = "POSTGRES_USER",        value = local.provsys_creds.rds_username },
        { name = "SQL_HOST",             value = aws_db_instance.prov-sys.address },
        { name = "SQL_PORT",             value = tostring(local.provsys_creds.rds_port) },
        { name = "DJANGO_ALLOWED_HOSTS", value = var.django_settings_allowed_hosts },
        { name = "CSRF_TRUSTED_ORIGINS", value = var.django_csrf_trusted_origins },
        { name = "REDIS_HOST",           value = var.redis_host },
        { name = "PS_SERVER_HOST",       value = var.ps_server_host },
        { name = "PS_SERVER_PORT",       value = tostring(local.ps_server_port_safe) },
        { name = "GRPC_POLL_STRATEGY",   value = "poll" },
        { name = "GRPC_DNS_RESOLVER",    value = "native" },
        { name = "DOMAIN",               value = var.domain },
        { name = "PS_VERSION",           value = var.ps_version },
        { name = "PS_SITE_TITLE",        value = var.ps_site_title },
        { name = "PS_BLD_ENVVER",        value = var.ps_bld_envver },
        { name = "SITE_ID",              value = tostring(var.site_id) }
      ]

      secrets = [
        { name = "DJANGO_SECRET_KEY",           valueFrom = "${local.provsys_secret_arn}:django_secret_key::" },
        { name = "JWT_SECRET_KEY",              valueFrom = "${local.provsys_secret_arn}:jwt_secret_key::" },
        { name = "POSTGRES_PASSWORD",           valueFrom = "${local.provsys_secret_arn}:rds_password::" },
        { name = "DJANGO_OIDC_RSA_PRIVATE_KEY", valueFrom = "${local.provsys_secret_arn}:oidc_rsa_key::" }
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options   = merge(local.common_log_opts, { "awslogs-stream-prefix" = "${var.domain_root}-ps-web" })
      }
    },

    {
      name         = "ps-nginx"
      image        = var.docker_image_url_ps-nginx
      essential    = true
      dependsOn    = [{ containerName = "ps-web", condition = "START" }]
      portMappings = [{ containerPort = tonumber(var.nginx_port), protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options   = merge(local.common_log_opts, { "awslogs-stream-prefix" = "${var.domain_root}-ps-nginx" })
      }
    }
  ]
}

#########################################################
# Task Definition with jsonencode
#########################################################

resource "aws_ecs_task_definition" "prov-sys" {
  family                   = "${var.domain_root}-prov-sys"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.prov-sys-fargate-cpu
  memory                   = var.prov-sys-fargate-memory
  execution_role_arn       = aws_iam_role.prov-sys-task-service-role.arn
  task_role_arn            = aws_iam_role.prov-sys-task-role.arn

  container_definitions = jsonencode(local.container_definitions)

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = var.runtime_cpu_arch
  }

  depends_on = [
    aws_db_instance.prov-sys,
    aws_iam_role.prov-sys-task-role,
    aws_iam_role.prov-sys-task-service-role
  ]

  tags = {
    Name = "${var.domain_root}-ps-ecs-tsk"
  }
}

#########################################################
# ECS Service (unchanged, still points at task def above)
#########################################################

resource "aws_ecs_service" "prov-sys-ecs-service" {
  name                = "${var.domain_root}-ps-srvc"
  cluster             = aws_ecs_cluster.prov-sys.id
  task_definition     = aws_ecs_task_definition.prov-sys.arn
  desired_count       = var.ps_web_task_count
  launch_type         = "FARGATE"
  enable_execute_command = true
  depends_on          = [aws_alb_listener.ps-web-http-listener]

  network_configuration {
    security_groups = [aws_security_group.ecs-ps-web.id]
    subnets         = [aws_subnet.private-subnet-1.id, aws_subnet.private-subnet-2.id]
  }

  load_balancer {
    target_group_arn = aws_alb_target_group.ps-web-target-group.arn
    container_name   = "ps-nginx"
    container_port   = 80
  }

  tags = {
    Name = "${var.domain_root}-ps-srvc"
  }
}
