locals {
  name_prefix       = "${var.project_name}-${var.environment}"
  availability_zone = var.availability_zone != "" ? var.availability_zone : data.aws_availability_zones.available.names[0]
  create_cpu        = var.enable_stack && var.create_cpu_instance
  create_gpu        = var.enable_stack && var.create_gpu_instance
}
