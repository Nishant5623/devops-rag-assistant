variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment (production/staging)"
  type        = string
  default     = "production"
}

variable "node_desired_size" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 2
}

variable "node_min_size" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 1
}

variable "node_max_size" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 4
}

variable "image_repository" {
  description = <<-EOT
    Container image repository to deploy. Must match the registry CI actually
    pushes to (.github/workflows/ci.yml pushes to GHCR). Pointing this at the
    ECR repo created below would deploy an image reference that never receives
    a push, and the pods would fail with ImagePullBackOff.
  EOT
  type        = string
  default     = "ghcr.io/nishant5623/devops-rag-assistant"
}

variable "image_tag" {
  description = <<-EOT
    Immutable container image tag to deploy. Deliberately has no default: a
    plan fails until you set it, because :latest is mutable and a node that
    already holds it will not re-pull - a re-apply can silently keep running
    old bytes. Set it to the commit sha CI pushed to GHCR, e.g.
    TF_VAR_image_tag=$(git rev-parse HEAD).
  EOT
  type        = string
}

variable "admin_api_key" {
  description = "Admin API key for protected endpoints (set via TF_VAR_admin_api_key)"
  type        = string
  sensitive   = true
}

variable "ingress_host" {
  description = "Public hostname for the ingress"
  type        = string
  default     = "rag.example.com"
}
