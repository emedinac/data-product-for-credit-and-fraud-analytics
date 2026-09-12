variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "europe-west3"
}

variable "container_image" {
  type = string
}

variable "db_password" {
  description = "Database password. Supply through a secure CI variable or Secret Manager workflow; do not commit it or put it in .env."
  type      = string
  sensitive = true
}

variable "sql_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "invoker_members" {
  description = "IAM principals allowed to invoke Cloud Run, for example serviceAccount:consumer@example.iam.gserviceaccount.com."
  type        = list(string)
  default     = []
}

variable "auth_audience" {
  description = "OAuth audience accepted by the API, normally the deployed Cloud Run service URL."
  type        = string
}

variable "auth_role_bindings" {
  description = "Non-secret JSON mapping of OAuth email/subject to application role."
  type        = string
  default     = "{}"
}
