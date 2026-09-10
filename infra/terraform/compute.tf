resource "aws_instance" "cpu" {
  count = local.create_cpu ? 1 : 0

  ami                    = data.aws_ssm_parameter.cpu_ami[0].value
  instance_type          = var.cpu_instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.cpu[0].id]
  iam_instance_profile   = aws_iam_instance_profile.this[0].name

  associate_public_ip_address = true
  user_data = templatefile("${path.module}/templates/cpu-user-data.sh.tftpl", {
    docker_compose_version = var.docker_compose_version
  })

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.cpu_root_volume_gib
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name = "${local.name_prefix}-cpu"
    Role = "application"
  }

  depends_on = [aws_iam_role_policy_attachment.ssm]
}

resource "aws_instance" "gpu" {
  count = local.create_gpu ? 1 : 0

  ami                    = local.gpu_ami_id
  instance_type          = var.gpu_instance_type
  subnet_id              = aws_subnet.public[0].id
  vpc_security_group_ids = [aws_security_group.gpu[0].id]
  iam_instance_profile   = aws_iam_instance_profile.this[0].name

  associate_public_ip_address = true
  user_data = templatefile("${path.module}/templates/gpu-user-data.sh.tftpl", {
    vllm_image = var.vllm_image
  })

  dynamic "instance_market_options" {
    for_each = var.gpu_use_spot ? [1] : []
    content {
      market_type = "spot"
      spot_options {
        instance_interruption_behavior = "terminate"
        spot_instance_type             = "one-time"
      }
    }
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.gpu_root_volume_gib
    encrypted             = true
    delete_on_termination = true
  }

  tags = {
    Name = "${local.name_prefix}-gpu"
    Role = "inference"
  }

  depends_on = [aws_iam_role_policy_attachment.ssm]
}
