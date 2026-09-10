provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile == "" ? null : var.aws_profile

  default_tags {
    tags = merge(var.tags, {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    })
  }
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_ssm_parameter" "cpu_ami" {
  count = var.enable_stack && var.create_cpu_instance ? 1 : 0
  name  = var.cpu_ami_ssm_parameter
}

data "aws_ssm_parameter" "gpu_ami" {
  count = var.enable_stack && var.create_gpu_instance && var.gpu_ami_id == "" ? 1 : 0
  name  = var.gpu_ami_ssm_parameter
}
