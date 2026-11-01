variable "region" {
  description = "AWS region (the pdfplumber layer must exist in this region)"
  type        = string
  default     = "us-east-2"
}

variable "name_prefix" {
  description = "Prefix for resource names, so this stack does not clash with the console-built one"
  type        = string
  default     = "invoice-tf"
}

variable "alert_email" {
  description = "Email address that receives the NEEDS_REVIEW / FAILED alarm"
  type        = string
}
