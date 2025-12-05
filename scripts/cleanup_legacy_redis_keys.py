#!/usr/bin/env python3
"""
Скрипт для очистки legacy Redis ключей после Phase 4 Cutover.

Sprint 19 Phase 4: Удаляет ключи от legacy HealthReporter (PUSH модель).

Удаляемые ключи:
- storage:elements:{se_id} - Hash с метаданными SE (HealthReporter)
- storage:rw:by_priority - Sorted set для RW режима (HealthReporter)
- storage:edit:by_priority - Sorted set для Edit режима (HealthReporter)

НЕ удаляются (используются AdaptiveCapacityMonitor):
- capacity:{se_id} - Capacity данные (POLLING модель)
- health:{se_id} - Health статус (POLLING модель)
- capacity:{mode}:available - Sorted sets (POLLING модель)
- capacity_monitor:leader_lock - Leader lock (POLLING модель)

Usage:
    # Dry run (только показать что будет удалено)
    python scripts/cleanup_legacy_redis_keys.py --dry-run

    # Реальное удаление
    python scripts/cleanup_legacy_redis_keys.py --execute

    # С кастомным Redis URL
    python scripts/cleanup_legacy_redis_keys.py --execute --redis-url redis://localhost:6379/0

Автор: Claude Code
Дата: Sprint 19 Phase 4 Cutover
"""

import argparse
import asyncio
import sys
from datetime import datetime

try:
    import redis.asyncio as aioredis
except ImportError:
    print("ERROR: redis.asyncio не установлен. Установите: pip install redis")
    sys.exit(1)


# Legacy ключи от HealthReporter (PUSH модель)
LEGACY_PATTERNS = [
    "storage:elements:*",      # Hash с метаданными SE
    "storage:rw:by_priority",  # Sorted set для RW режима
    "storage:edit:by_priority", # Sorted set для Edit режима
]


async def get_legacy_keys(redis_client) -> dict:
    """
    Поиск всех legacy ключей в Redis.

    Returns:
        dict: {pattern: [keys]}
    """
    result = {}

    for pattern in LEGACY_PATTERNS:
        if "*" in pattern:
            # Паттерн с wildcard - используем SCAN
            keys = []
            async for key in redis_client.scan_iter(match=pattern, count=100):
                keys.append(key)
            result[pattern] = keys
        else:
            # Конкретный ключ - проверяем существование
            exists = await redis_client.exists(pattern)
            result[pattern] = [pattern] if exists else []

    return result


async def delete_keys(redis_client, keys: list, dry_run: bool) -> int:
    """
    Удаление ключей из Redis.

    Args:
        redis_client: Redis клиент
        keys: Список ключей для удаления
        dry_run: Только показать, не удалять

    Returns:
        int: Количество удаленных ключей
    """
    if not keys:
        return 0

    if dry_run:
        return len(keys)

    # Удаляем батчами по 100 ключей
    deleted = 0
    batch_size = 100

    for i in range(0, len(keys), batch_size):
        batch = keys[i:i + batch_size]
        deleted += await redis_client.delete(*batch)

    return deleted


async def main(args):
    """Основная логика скрипта."""

    print("=" * 60)
    print("Legacy Redis Keys Cleanup - Sprint 19 Phase 4")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Redis URL: {args.redis_url}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print()

    # Подключение к Redis
    try:
        redis_client = await aioredis.from_url(
            args.redis_url,
            decode_responses=True
        )
        await redis_client.ping()
        print("✅ Redis connected successfully")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return 1

    try:
        # Поиск legacy ключей
        print("\n📋 Searching for legacy keys...")
        legacy_keys = await get_legacy_keys(redis_client)

        total_keys = 0
        all_keys_to_delete = []

        for pattern, keys in legacy_keys.items():
            count = len(keys)
            total_keys += count
            all_keys_to_delete.extend(keys)

            if count > 0:
                print(f"\n  Pattern: {pattern}")
                print(f"  Found: {count} key(s)")
                if count <= 10:
                    for key in keys:
                        print(f"    - {key}")
                else:
                    for key in keys[:5]:
                        print(f"    - {key}")
                    print(f"    ... and {count - 5} more")

        print(f"\n📊 Total legacy keys found: {total_keys}")

        if total_keys == 0:
            print("\n✅ No legacy keys to clean up!")
            return 0

        # Удаление ключей
        if args.dry_run:
            print("\n⚠️  DRY RUN - No keys were deleted")
            print("   Run with --execute to actually delete keys")
        else:
            print("\n🗑️  Deleting legacy keys...")
            deleted = await delete_keys(redis_client, all_keys_to_delete, dry_run=False)
            print(f"✅ Deleted {deleted} key(s)")

        # Проверка что новые ключи на месте
        print("\n🔍 Verifying new POLLING model keys...")

        new_patterns = [
            "capacity:*",
            "health:*",
            "capacity_monitor:leader_lock",
        ]

        for pattern in new_patterns:
            if "*" in pattern:
                count = 0
                async for _ in redis_client.scan_iter(match=pattern, count=100):
                    count += 1
                print(f"  {pattern}: {count} key(s)")
            else:
                exists = await redis_client.exists(pattern)
                status = "✅ exists" if exists else "⚠️ not found"
                print(f"  {pattern}: {status}")

        print("\n" + "=" * 60)
        print("Cleanup completed successfully!")
        print("=" * 60)

        return 0

    finally:
        await redis_client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cleanup legacy Redis keys from HealthReporter (PUSH model)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be deleted, don't actually delete"
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete the legacy keys"
    )

    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379/0",
        help="Redis connection URL (default: redis://localhost:6379/0)"
    )

    args = parser.parse_args()

    # Требуем явного указания режима
    if not args.dry_run and not args.execute:
        print("ERROR: Must specify either --dry-run or --execute")
        parser.print_help()
        sys.exit(1)

    if args.dry_run and args.execute:
        print("ERROR: Cannot specify both --dry-run and --execute")
        sys.exit(1)

    # Запуск
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)
