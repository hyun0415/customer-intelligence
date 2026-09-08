data "aws_iam_policy_document" "ec2_assume_role" {
  count = var.enable_stack ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  count = var.enable_stack ? 1 : 0

  name               = "${local.name_prefix}-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role[0].json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  count = var.enable_stack ? 1 : 0

  role       = aws_iam_role.instance[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "this" {
  count = var.enable_stack ? 1 : 0

  name = "${local.name_prefix}-instance"
  role = aws_iam_role.instance[0].name
}
