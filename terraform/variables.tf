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

variable "bedrock_foundation_model" {
  description = "Bedrock foundation model used by the LLM fallback"
  type        = string
  default     = "amazon.nova-2-lite-v1:0"
}

variable "bedrock_inference_profile" {
  description = "US cross-region inference profile for that model (Nova 2 Lite cannot be called in-region from us-east-2)"
  type        = string
  default     = "us.amazon.nova-2-lite-v1:0"
}
