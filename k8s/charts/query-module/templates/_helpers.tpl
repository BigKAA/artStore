{{- define "query.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: artstore
app.kubernetes.io/name: query-module
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "query.selectorLabels" -}}
app.kubernetes.io/name: query-module
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "query.image" -}}
{{ .Values.registry }}/{{ .Values.image }}:{{ .Values.tag }}
{{- end }}
