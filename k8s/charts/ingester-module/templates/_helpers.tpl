{{- define "ingester.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: artstore
app.kubernetes.io/name: ingester-module
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "ingester.selectorLabels" -}}
app.kubernetes.io/name: ingester-module
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "ingester.image" -}}
{{ .Values.registry }}/{{ .Values.image }}:{{ .Values.tag }}
{{- end }}
