output "aws_account_id" {
  value = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  value = var.aws_region
}

output "cpu_instance_id" {
  value = try(aws_instance.cpu[0].id, null)
}

output "cpu_private_ip" {
  value = try(aws_instance.cpu[0].private_ip, null)
}

output "gpu_instance_id" {
  value = try(aws_instance.gpu[0].id, null)
}

output "gpu_private_ip" {
  value = try(aws_instance.gpu[0].private_ip, null)
}

output "cpu_to_gpu_vllm_base_url" {
  value = local.create_cpu && local.create_gpu ? "http://${aws_instance.gpu[0].private_ip}:8000/v1" : null
}

output "cpu_to_gpu_structured_base_url" {
  value = local.create_cpu && local.create_gpu ? "http://${aws_instance.gpu[0].private_ip}:8002/v1" : null
}

output "cpu_to_gpu_reranker_base_url" {
  value = local.create_cpu && local.create_gpu ? "http://${aws_instance.gpu[0].private_ip}:8003" : null
}

output "access_note" {
  value = "No inbound ports are public. Use AWS Systems Manager Session Manager or port forwarding."
}

output "ecr_repository_urls" {
  value = { for name, repository in aws_ecr_repository.images : name => repository.repository_url }
}
