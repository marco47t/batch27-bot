#!/bin/bash
# Database backup script
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$HOME/backups"
mkdir -p "$BACKUP_DIR"

# Replace with your actual RDS endpoint
pg_dump -h batch27-bot-db1.c56eig6oa09g.eu-north-1.rds.amazonaws.com -U postgres -d postgres > "$BACKUP_DIR/backup_$DATE.sql"

# Keep only last 7 days
find "$BACKUP_DIR" -name "backup_*.sql" -mtime +7 -delete

echo "Backup completed: backup_$DATE.sql"
