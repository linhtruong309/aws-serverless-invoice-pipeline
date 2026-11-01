import datetime
import os
import urllib.parse

import boto3

from invoice_parser import parse_invoice

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ.get("TABLE_NAME", "invoices"))


def lambda_handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

        try:
            parsed = parse_invoice(body)
            status = "PARSED" if not parsed["issues"] else "NEEDS_REVIEW"
        except Exception as exc:  # unreadable or unexpected PDF
            print(f"ERROR parsing {key}: {exc}")
            parsed, status = {"issues": [f"parser error: {exc}"]}, "FAILED"

        item = {
            "source_key": key,
            "bucket": bucket,
            "status": status,
            "received_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            **{k: v for k, v in parsed.items() if v is not None},
        }
        table.put_item(Item=item)
        print(f"Saved {key}: {status} issues={parsed.get('issues')}")
    return {"status": "ok"}
