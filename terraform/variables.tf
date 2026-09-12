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
  type      = string
  sensitive = true
}

variable "sql_tier" {
  type    = string
  default = "db-f1-micro"
}
