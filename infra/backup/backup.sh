#!/bin/sh
set -eu
umask 077
: "${S3_BUCKET:?Set S3_BUCKET}"
: "${S3_KMS_KEY_ID:?Set S3_KMS_KEY_ID}"
: "${AWS_DEFAULT_REGION:?Set AWS_DEFAULT_REGION}"
export PGHOST=db PGDATABASE=gold PGUSER=gold_reader
PGPASSWORD="$(cat /run/secrets/db_reader_password)"
export PGPASSWORD
task_dir="$(mktemp -d /tmp/gold-backup.XXXXXX)"
trap 'rm -f "$task_dir/gold.dump" "$task_dir/gold.dump.sha256"; rmdir "$task_dir"' EXIT INT TERM
pg_dump --format=custom --no-owner --no-acl --file "$task_dir/gold.dump"
pg_restore --list "$task_dir/gold.dump" > /dev/null
cd "$task_dir"
sha256sum gold.dump > gold.dump.sha256
backup_key="gold/$(date -u +%Y/%m/%d/%Y%m%dT%H%M%SZ)"
aws s3 cp gold.dump "s3://$S3_BUCKET/$backup_key/gold.dump" --sse aws:kms --sse-kms-key-id "$S3_KMS_KEY_ID" --only-show-errors
aws s3 cp gold.dump.sha256 "s3://$S3_BUCKET/$backup_key/gold.dump.sha256" --sse aws:kms --sse-kms-key-id "$S3_KMS_KEY_ID" --only-show-errors
printf '{"event":"backup_uploaded","status":"success"}\n'
