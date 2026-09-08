resource "aws_security_group" "cpu" {
  count = local.create_cpu ? 1 : 0

  name        = "${local.name_prefix}-cpu"
  description = "CPU application host; interactive access is through SSM only"
  vpc_id      = aws_vpc.this[0].id

  tags = { Name = "${local.name_prefix}-cpu" }
}

resource "aws_vpc_security_group_egress_rule" "cpu_ipv4" {
  count = local.create_cpu ? 1 : 0

  security_group_id = aws_security_group.cpu[0].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Package, image, OIDC, and model endpoint access"
}

resource "aws_security_group" "gpu" {
  count = local.create_gpu ? 1 : 0

  name        = "${local.name_prefix}-gpu"
  description = "GPU inference host; no public inbound access"
  vpc_id      = aws_vpc.this[0].id

  tags = { Name = "${local.name_prefix}-gpu" }
}

resource "aws_vpc_security_group_egress_rule" "gpu_ipv4" {
  count = local.create_gpu ? 1 : 0

  security_group_id = aws_security_group.gpu[0].id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Container image and Hugging Face model downloads"
}

resource "aws_vpc_security_group_ingress_rule" "gpu_from_cpu" {
  count = local.create_cpu && local.create_gpu ? 1 : 0

  security_group_id            = aws_security_group.gpu[0].id
  referenced_security_group_id = aws_security_group.cpu[0].id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  description                  = "OpenAI-compatible vLLM endpoint from the CPU application host"
}
