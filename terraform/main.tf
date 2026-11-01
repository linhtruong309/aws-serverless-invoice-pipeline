terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.23, < 7.0" # 6.23+ understands credentials from `aws login`
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "aws-serverless-invoice-pipeline"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

resource "random_id" "suffix" {
  byte_length = 4
}

# ---------------------------------------------------------------- storage
resource "aws_s3_bucket" "input" {
  bucket        = "${var.name_prefix}-input-${random_id.suffix.hex}"
  force_destroy = true # lets `terraform destroy` delete the bucket even if it holds sample PDFs
}

resource "aws_s3_bucket_public_access_block" "input" {
  bucket                  = aws_s3_bucket.input.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "invoices" {
  name         = "${var.name_prefix}-invoices"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "source_key"

  attribute {
    name = "source_key"
    type = "S"
  }
}

# ---------------------------------------------------------------- lambda
# Zips everything in ../src (invoice_parser.py + lambda_function.py)
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/lambda.zip"
  excludes    = ["__pycache__", "__pycache__/*"]
}

# The pdfplumber layer you built earlier in CloudShell (latest version)
data "aws_lambda_layer_version" "pdfplumber" {
  layer_name = "pdfplumber"
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.name_prefix}-parser"
  retention_in_days = 7
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Least privilege: read objects from this bucket, write items to this table
data "aws_iam_policy_document" "lambda" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.input.arn}/*"]
  }
  statement {
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.invoices.arn]
  }
  # LLM fallback: allowed to call exactly one model, through its US cross-region inference profile
  statement {
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${var.region}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.bedrock_inference_profile}",
      "arn:aws:bedrock:*::foundation-model/${var.bedrock_foundation_model}",
    ]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "least-privilege"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_lambda_function" "parser" {
  function_name    = "${var.name_prefix}-parser"
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "lambda_function.lambda_handler"
  architectures    = ["x86_64"]
  memory_size      = 512
  timeout          = 60
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  layers           = [data.aws_lambda_layer_version.pdfplumber.arn]

  environment {
    variables = {
      TABLE_NAME       = aws_dynamodb_table.invoices.name
      BEDROCK_MODEL_ID = var.bedrock_inference_profile
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy_attachment.logs,
  ]
}

# ---------------------------------------------------------------- S3 -> Lambda trigger
resource "aws_lambda_permission" "s3" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.parser.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.input.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "input" {
  bucket = aws_s3_bucket.input.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.parser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".pdf"
  }

  depends_on = [aws_lambda_permission.s3]
}

# ---------------------------------------------------------------- monitoring
resource "aws_cloudwatch_log_metric_filter" "review" {
  name           = "InvoicesNeedingReview"
  log_group_name = aws_cloudwatch_log_group.lambda.name
  pattern        = "?\"NEEDS_REVIEW\" ?\"FAILED\""

  metric_transformation {
    name          = "InvoicesNeedingReview"
    namespace     = "InvoicePipelineTF"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-review-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "review" {
  alarm_name          = "${var.name_prefix}-needs-review"
  namespace           = "InvoicePipelineTF"
  metric_name         = "InvoicesNeedingReview"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
