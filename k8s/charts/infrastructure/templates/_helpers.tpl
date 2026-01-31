{{- define "infra.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: artstore
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}
