#!/bin/sh
set -e

echo "Waiting for MinIO to start..."
sleep 10

# Setup mc alias
until mc alias set myminio http://localhost:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} 2>/dev/null; do
  echo "Waiting for MinIO to be ready..."
  sleep 2
done

mc admin user add myminio admin ${MINIO_ROOT_PASSWORD}
mc admin policy attach myminio diagnostics --user admin
mc admin policy attach myminio diagnostics --user admin
mc admin policy attach myminio consoleAdmin --user admin


# Create admin user with full access
mc admin user add myminio admin ${MINIO_ROOT_PASSWORD}123
mc admin policy attach myminio fullaccess --user admin

