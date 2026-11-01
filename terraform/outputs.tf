output "bucket_name" {
  description = "Upload invoice PDFs here"
  value       = aws_s3_bucket.input.bucket
}

output "table_name" {
  description = "DynamoDB table holding parsed invoices"
  value       = aws_dynamodb_table.invoices.name
}

output "lambda_name" {
  value = aws_lambda_function.parser.function_name
}

output "alarm_name" {
  value = aws_cloudwatch_metric_alarm.review.alarm_name
}
