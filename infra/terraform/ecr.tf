locals {
  image_repositories = toset(["backend", "frontend", "reranker"])
}

resource "aws_ecr_repository" "images" {
  for_each = var.enable_stack ? local.image_repositories : toset([])

  name                 = "${var.project_name}/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = var.ecr_force_delete

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = { Name = "${local.name_prefix}-${each.key}" }
}

resource "aws_ecr_lifecycle_policy" "images" {
  for_each = aws_ecr_repository.images

  repository = each.value.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the latest ten validation images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

data "aws_iam_policy_document" "ecr_pull" {
  count = var.enable_stack ? 1 : 0

  statement {
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [for repository in aws_ecr_repository.images : repository.arn]
  }
}

resource "aws_iam_role_policy" "ecr_pull" {
  count = var.enable_stack ? 1 : 0

  name   = "${local.name_prefix}-ecr-pull"
  role   = aws_iam_role.instance[0].id
  policy = data.aws_iam_policy_document.ecr_pull[0].json
}
