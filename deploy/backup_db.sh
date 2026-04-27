#!/bin/bash
# Ella Telegram Bot — SQLite DB 자동 백업
# cron: 0 3 * * * /home/swiri021/ella-telegram/deploy/backup_db.sh

set -e

DB_PATH="/home/swiri021/ella-telegram/data/chat.db"
BACKUP_DIR="/home/swiri021/ella-telegram/backups"
KEEP_DAYS=7

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

# SQLite .backup 명령 (WAL 호환, 핫 백업 안전)
BACKUP_FILE="$BACKUP_DIR/chat_$(date +%Y%m%d_%H%M%S).db"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# 오래된 백업 삭제 (7일 초과)
find "$BACKUP_DIR" -name "chat_*.db" -mtime +$KEEP_DAYS -delete

echo "$(date): 백업 완료 → $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
