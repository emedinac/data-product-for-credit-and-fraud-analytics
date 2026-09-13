terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_project_service" "services" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "api" {
  location      = var.region
  repository_id = "customer-data-product"
  format        = "DOCKER"
  depends_on    = [google_project_service.services]
}

resource "google_storage_bucket" "lake" {
  name                        = "${var.project_id}-customer-data-lake"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  depends_on                  = [google_project_service.services]
}

resource "google_sql_database_instance" "postgres" {
  name                = "customer-data-postgres"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = true
  settings {
    tier              = var.sql_tier
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 10
    backup_configuration { enabled = true }
  }
  depends_on = [google_project_service.services]
}

resource "google_sql_database" "app" {
  name     = "customer_product"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  name     = "customer"
  instance = google_sql_database_instance.postgres.name
  password = var.db_password
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "customer-data-db-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}

resource "google_service_account" "api" {
  account_id   = "customer-data-api"
  display_name = "Customer Data API"
}

resource "google_project_iam_member" "cloud_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "lake_access" {
  bucket = google_storage_bucket.lake.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "db_password_access" {
  secret_id = google_secret_manager_secret.db_password.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_service_account" "grafana" {
  account_id   = "customer-data-grafana"
  display_name = "Customer Data Grafana viewer"
}

resource "google_project_iam_member" "grafana_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.grafana.email}"
}

resource "google_monitoring_notification_channel" "email" {
  count        = var.notification_email == null ? 0 : 1
  display_name = "Customer Data Product alerts"
  type         = "email"
  labels       = { email_address = var.notification_email }
}

locals {
  notification_channels = concat(
    var.notification_channel_ids,
    var.notification_email == null ? [] : [
      google_monitoring_notification_channel.email[0].id
    ],
  )
  metric_prefix = "workload.googleapis.com/customer_data_product_"
}

resource "google_monitoring_alert_policy" "freshness" {
  display_name          = "Customer Data Product freshness"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Freshness exceeds 24 hours"
    condition_threshold {
      filter          = "metric.type=\"${local.metric_prefix}freshness_seconds\""
      comparison      = "COMPARISON_GT"
      threshold_value = 86400
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "quality" {
  display_name          = "Customer Data Product quality failure"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Quality gate failed"
    condition_threshold {
      filter          = "metric.type=\"${local.metric_prefix}quality_failures_total\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "processing" {
  display_name          = "Customer Data Product processing failure"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Processing failed"
    condition_threshold {
      filter          = "metric.type=\"${local.metric_prefix}processing_failures_total\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "source_schema_drift" {
  display_name          = "Customer Data Product source schema drift"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Source records no longer match required fields"
    condition_threshold {
      filter          = "metric.type=\"${local.metric_prefix}source_schema_drift_total\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "pipeline_sla" {
  display_name          = "Customer Data Product end-to-end SLA"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Published batch exceeded the 24-hour SLA"
    condition_threshold {
      filter          = "metric.type=\"${local.metric_prefix}sla_breaches_total\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "composer_health" {
  count                 = var.composer_environment_name == null ? 0 : 1
  display_name          = "Customer Data Product Airflow health"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Cloud Composer environment is unhealthy"
    condition_threshold {
      filter          = "resource.type=\"cloud_composer_environment\" metric.type=\"composer.googleapis.com/environment/healthy\" resource.label.environment_name=\"${var.composer_environment_name}\""
      comparison      = "COMPARISON_LT"
      threshold_value = 0.9
      duration        = "14400s"
      aggregations {
        alignment_period   = "14400s"
        per_series_aligner = "ALIGN_FRACTION_TRUE"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "composer_dependencies" {
  count                 = var.composer_environment_name == null ? 0 : 1
  display_name          = "Customer Data Product Airflow dependency failure"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Cloud Composer dependency check failed"
    condition_threshold {
      filter          = "resource.type=\"cloud_composer_environment\" metric.type=\"composer.googleapis.com/environment/health/dependency_check_count\" resource.label.environment_name=\"${var.composer_environment_name}\" metric.label.status!=\"OK\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "api_errors" {
  display_name          = "Customer Data Product API errors"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Cloud Run returned 5xx responses"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" resource.type=\"cloud_run_revision\" metric.labels.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "300s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }
}

resource "google_monitoring_alert_policy" "volume" {
  display_name          = "Customer Data Product volume anomaly"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Volume change exceeds 50 percent"
    condition_threshold {
      filter          = "metric.type=\"${local.metric_prefix}volume_change_ratio\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.5
      duration        = "0s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }
}

resource "google_monitoring_uptime_check_config" "health" {
  display_name = "Customer Data Product health"
  timeout      = "10s"
  http_check {
    path    = "/health"
    port    = 443
    use_ssl = true
  }
  monitored_resource {
    type   = "uptime_url"
    labels = { host = replace(google_cloud_run_v2_service.api.uri, "https://", "") }
  }
}

resource "google_monitoring_alert_policy" "downtime" {
  display_name          = "Customer Data Product downtime"
  combiner              = "OR"
  notification_channels = local.notification_channels
  conditions {
    display_name = "Health check failed"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" resource.type=\"uptime_url\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_FRACTION_TRUE"
      }
    }
  }
}

resource "google_cloud_run_v2_service" "api" {
  name                = "customer-data-api"
  location            = var.region
  deletion_protection = false
  depends_on          = [google_project_service.services]
  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance { instances = [google_sql_database_instance.postgres.connection_name] }
    }
    containers {
      image = var.container_image
      ports {
        container_port = 8080
      }
      env {
        name  = "STORAGE_BACKEND"
        value = "gcs"
      }
      env {
        name  = "STORAGE_BUCKET"
        value = google_storage_bucket.lake.name
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "AUTH_AUDIENCE"
        value = var.auth_audience
      }
      env {
        name  = "AUTH_ROLE_BINDINGS"
        value = var.auth_role_bindings
      }
      env {
        name  = "DATABASE_URL"
        value = "postgresql://customer@/customer_product?host=/cloudsql/${google_sql_database_instance.postgres.connection_name}"
      }
      env {
        name = "PGPASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_password.secret_id
            version = "latest"
          }
        }
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)
  name     = google_cloud_run_v2_service.api.name
  location = google_cloud_run_v2_service.api.location
  role     = "roles/run.invoker"
  member   = each.value
}
