{{- define "microservices.fullname" -}}
{{ printf "%s-%s" .Release.Name .Name | trunc 63 | trimSuffix "-" }}
{{- end -}}
