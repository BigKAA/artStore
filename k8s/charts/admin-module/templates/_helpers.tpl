{{- define "admin.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: artstore
app.kubernetes.io/name: admin-module
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "admin.selectorLabels" -}}
app.kubernetes.io/name: admin-module
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "admin.image" -}}
{{ .Values.registry }}/{{ .Values.image }}:{{ .Values.tag }}
{{- end }}
