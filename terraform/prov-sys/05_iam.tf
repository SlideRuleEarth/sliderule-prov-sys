
# ---------------------------------------------------------------------------------------------------------------------
# generic ECS service assume role policy
# ---------------------------------------------------------------------------------------------------------------------
data "aws_iam_policy_document" "tasks-service-assume-policy" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}
# ---------------------------------------------------------------------------------------------------------------------
# ECS execution ROLE for prov-sys
# ---------------------------------------------------------------------------------------------------------------------
resource "aws_iam_role" "prov-sys-task-service-role" {
  name               = "${var.domain_root}-ps-tsr" 
  path               = "/"
  assume_role_policy = data.aws_iam_policy_document.tasks-service-assume-policy.json
}

resource "aws_iam_role_policy_attachment" "prov-sys-task-service-role-attachment" {
  role       = aws_iam_role.prov-sys-task-service-role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

#-------------------------------------------------------------------------------------------------------------------
# ECS task ROLE for prov-sys
# ---------------------------------------------------------------------------------------------------------------------
resource "aws_iam_role" "prov-sys-task-role" {
  name = "${var.domain_root}-ps-tr"
 
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
 ]
}
EOF
}
# ---------------------------------------------------------------------------------------------------------------------
# policy for prov-sys fargate ecs tasks service
# ---------------------------------------------------------------------------------------------------------------------

resource "aws_iam_policy" "prov-sys-fargate" {
  name        = "${var.domain_root}-ps-PlcyFG"
  description = "Policy that allows FARGATE ecs services for prov-sys"
 
  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
        "Effect": "Allow",
        "Action": [
            "cloudwatch:*",
            "logs:*",
            "ecs:*"
        ],
        "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    },
    {
        "Effect": "Allow",
        "Action": [
            "s3:ListBucket",
            "s3:GetBucketLocation",
            "cloudwatch:*",
            "logs:*",
            "ecs:*"
        ],
        "Resource": "*"
    },
    {
        "Effect": "Allow",
        "Action": [
            "s3:PutObject",
            "s3:GetObject"
        ],
        "Resource": "arn:aws:s3:::sliderule/*"
    }
  ]
}
EOF
}


# ---------------------------------------------------------------------------------------------------------------------
# policy for prov-sys task 
# ---------------------------------------------------------------------------------------------------------------------

resource "aws_iam_policy" "prov_sys" {
  name        = "${var.domain_root}-ps-tsk"
  description = "Policy that allows a django server to access aws services and ps-server to provision data science clusters"
 
  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
        "Effect": "Allow",
        "Action": [
          "ses:SendRawEmail"
        ],
        "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    },
    {
        "Effect": "Allow",
        "Action": [
            "iam:TagRole",
            "iam:TagPolicy",
            "iam:TagInstanceProfile",
            "iam:GetPolicy",
            "iam:ListPolicyVersions",
            "iam:GetPolicyVersion",
            "iam:CreatePolicy",
            "iam:DeletePolicy",
            "iam:CreateInstanceProfile",
            "iam:GetInstanceProfile",
            "iam:AttachRolePolicy",
            "iam:DetachRolePolicy",
            "iam:AddRoleToInstanceProfile",
            "iam:RemoveRoleFromInstanceProfile",
            "iam:DeleteInstanceProfile",
            "ce:getCostAndUsage",
            "ce:GetTags",
            "ec2:*",
            "ecs:*",
            "s3:*",
            "elasticloadbalancing:*",
            "route53:ListHostedZones",
            "route53:GetHostedZone",
            "route53:ChangeResourceRecordSets",
            "route53:ListResourceRecordSets",
            "route53:ListTagsForResource",
            "route53:GetChange",
            "autoscaling:*",
            "acm:GetCertificate",
            "acm:ListCertificates",
            "acm:DescribeCertificate",
            "acm:ListTagsForCertificate"
        ],
        "Resource": "*"
    },
    {
        "Effect": "Allow",
        "Action": [
            "iam:GetRole",
            "iam:CreateRole",
            "iam:PassRole",
            "iam:DeleteRole",
            "iam:ListRolePolicies",
            "iam:ListAttachedRolePolicies",
            "iam:ListInstanceProfilesForRole"
        ],
        "Resource": "arn:aws:iam::${local.provsys_creds.aws_account_id}:role/*"
    },
    {
        "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"],
        "Resource": "arn:aws:secretsmanager:*:${local.provsys_creds.aws_account_id}:secret:*"
    },
    {
      "Effect": "Allow",
      "Action": [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
      ],
      "Resource": "*"
    }  
  ]
}
EOF
}

######################################################################
# Attach prov-sys ECS policies

resource "aws_iam_role_policy_attachment" "prov-sys-task-role-policy-attachment" {
  role       = aws_iam_role.prov-sys-task-role.name
  policy_arn = aws_iam_policy.prov_sys.arn
} 
resource "aws_iam_role_policy_attachment" "prov-sys-ecs-tasks-service-role-policy-attachment" {
  role       = aws_iam_role.prov-sys-task-service-role.name
  policy_arn = aws_iam_policy.prov-sys-fargate.arn
}
