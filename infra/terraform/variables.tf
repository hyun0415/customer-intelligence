variable "enable_stack" {
  description = "Master safety switch. When false, Terraform creates no AWS resources."
  type        = bool
  default     = false
}

variable "create_cpu_instance" {
  description = "Create the CPU EC2 host for Next.js, FastAPI, PostgreSQL, and Redis."
  type        = bool
  default     = false
}

variable "create_gpu_instance" {
  description = "Create the GPU EC2 host for vLLM model validation."
  type        = bool
  default     = false
}

variable "aws_profile" {
  description = "Optional local AWS CLI profile used by Terraform. Leave empty for the default credential chain."
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "AWS Region that provides the selected GPU instance and AMI."
  type        = string
  default     = "ap-northeast-2"
}

variable "availability_zone" {
  description = "Optional single Availability Zone. The first available AZ is used when empty."
  type        = string
  default     = ""
}

variable "project_name" {
  type    = string
  default = "customer-intelligence"
}

variable "environment" {
  type    = string
  default = "validation"
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "public_subnet_cidr" {
  type    = string
  default = "10.42.10.0/24"
}

variable "cpu_ami_ssm_parameter" {
  description = "AWS public SSM parameter for the CPU host AMI."
  type        = string
  default     = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

variable "cpu_instance_type" {
  type    = string
  default = "t3.large"
}

variable "cpu_root_volume_gib" {
  type    = number
  default = 100

  validation {
    condition     = var.cpu_root_volume_gib >= 40
    error_message = "cpu_root_volume_gib must be at least 40 GiB."
  }
}

variable "gpu_ami_id" {
  description = "Optional region-specific Deep Learning GPU AMI ID override. When empty, gpu_ami_ssm_parameter is used."
  type        = string
  default     = ""
}

variable "gpu_ami_ssm_parameter" {
  description = "AWS public SSM parameter for the latest x86_64 Deep Learning Base GPU AMI."
  type        = string
  default     = "/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id"
}

variable "gpu_instance_type" {
  description = "GPU host size for sequential local-model validation."
  type        = string
  default     = "g6e.2xlarge"
}

variable "gpu_root_volume_gib" {
  type    = number
  default = 400

  validation {
    condition     = var.gpu_root_volume_gib >= 150
    error_message = "gpu_root_volume_gib must be at least 150 GiB for images and model cache."
  }
}

variable "gpu_use_spot" {
  description = "Use interruptible Spot capacity. Keep false for the first quality-validation run."
  type        = bool
  default     = false
}

variable "vllm_image" {
  description = "vLLM container image. Pin this to a tested tag or digest before recording benchmark results."
  type        = string
  default     = "vllm/vllm-openai:v0.28.0"
}

variable "docker_compose_version" {
  description = "Docker Compose plugin version installed on the CPU host."
  type        = string
  default     = "v2.40.3"
}

variable "ecr_force_delete" {
  description = "Allow Terraform destroy to remove validation repositories that still contain images."
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}

check "gpu_ami_is_set" {
  assert {
    condition     = var.gpu_ami_id == "" || can(regex("^ami-[0-9a-f]+$", var.gpu_ami_id))
    error_message = "gpu_ami_id must be empty or a valid AMI ID."
  }
}

check "at_least_one_host" {
  assert {
    condition     = !var.enable_stack || var.create_cpu_instance || var.create_gpu_instance
    error_message = "When enable_stack is true, enable at least one CPU or GPU instance."
  }
}
