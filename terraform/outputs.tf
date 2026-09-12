output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.api.name
}

output "storage_bucket" {
  value = google_storage_bucket.lake.name
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.postgres.connection_name
}

output "grafana_viewer_service_account" {
  value = google_service_account.grafana.email
}
