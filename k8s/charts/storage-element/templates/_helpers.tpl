{{- define "se.labels" -}}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: artstore
app.kubernetes.io/name: storage-element
app.kubernetes.io/component: {{ .Values.elementId }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "se.selectorLabels" -}}
app.kubernetes.io/name: storage-element
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Имя ресурсов = storage-element-<elementId> */}}
{{- define "se.fullname" -}}
storage-element-{{ .Values.elementId }}
{{- end }}

{{- define "se.image" -}}
{{ .Values.registry }}/{{ .Values.image }}:{{ .Values.tag }}
{{- end }}
