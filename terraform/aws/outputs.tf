output "cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  description = "ECR repository URL to push the app image to"
  value       = aws_ecr_repository.app.repository_url
}

output "helm_release_status" {
  description = "Status of the Helm release for the app"
  value       = helm_release.app.status
}
