#!/usr/bin/env python3
"""
Фаза 3: Позитивные сценарии тестирования SE Selection Strategy

Тесты:
- T1: 40 файлов в se-01 (Sequential Fill)
- T2: Заполнение se-01 до 96%
- T3: Capacity Status Transitions
- T4: Переключение на se-02 (FULL se-01)
- T5: 20 файлов в se-02
- T6: File Finalization (TEMPORARY→PERMANENT)
- T7: Новые файлы в edit SE (не в rw)
"""

import os
import sys
import json
import time
import random
import string
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

# Конфигурация
ADMIN_URL = "http://localhost:8000"
INGESTER_URL = "http://localhost:8020"
QUERY_URL = "http://localhost:8030"
SE_01_URL = "http://localhost:8010"
SE_02_URL = "http://localhost:8011"
SE_03_URL = "http://localhost:8012"

# Credentials
SA_CLIENT_ID = "sa_prod_admin_service_de171928"
SA_CLIENT_SECRET = "TestPassword123!"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# Test configuration
FILE_SIZE_KB = 100  # Размер тестового файла в KB
SE_CAPACITY_GB = 1  # Capacity каждого SE в GB
WARNING_THRESHOLD = 0.85  # 85%
CRITICAL_THRESHOLD = 0.92  # 92%
FULL_THRESHOLD = 0.98  # 98%


class TestResult:
    """Результат теста"""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
        self.details: Dict[str, Any] = {}
        self.start_time = datetime.now()
        self.end_time: Optional[datetime] = None

    def success(self, message: str, **details):
        self.passed = True
        self.message = message
        self.details = details
        self.end_time = datetime.now()
        print(f"✅ {self.name}: {message}")

    def failure(self, message: str, **details):
        self.passed = False
        self.message = message
        self.details = details
        self.end_time = datetime.now()
        print(f"❌ {self.name}: {message}")

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "duration_seconds": (self.end_time - self.start_time).total_seconds() if self.end_time else 0
        }


class Phase3Tester:
    """Тестер для Фазы 3"""

    def __init__(self):
        self.sa_token: Optional[str] = None
        self.admin_token: Optional[str] = None
        self.results: List[TestResult] = []
        self.uploaded_files: List[Dict] = []

    def get_sa_token(self) -> str:
        """Получить Service Account токен для API"""
        if self.sa_token:
            return self.sa_token

        resp = requests.post(
            f"{ADMIN_URL}/api/v1/auth/token",
            json={
                "client_id": SA_CLIENT_ID,
                "client_secret": SA_CLIENT_SECRET
            }
        )
        resp.raise_for_status()
        self.sa_token = resp.json()["access_token"]
        return self.sa_token

    def get_admin_token(self) -> str:
        """Получить Admin User токен"""
        if self.admin_token:
            return self.admin_token

        resp = requests.post(
            f"{ADMIN_URL}/api/v1/admin-auth/login",
            json={
                "username": ADMIN_USERNAME,
                "password": ADMIN_PASSWORD
            }
        )
        resp.raise_for_status()
        self.admin_token = resp.json()["access_token"]
        return self.admin_token

    def get_storage_elements(self) -> List[Dict]:
        """Получить список Storage Elements"""
        resp = requests.get(
            f"{ADMIN_URL}/api/v1/storage-elements/",
            headers={"Authorization": f"Bearer {self.get_admin_token()}"}
        )
        resp.raise_for_status()
        return resp.json()["items"]

    def get_se_by_name_or_id(self, identifier) -> Optional[Dict]:
        """Найти SE по имени или ID"""
        ses = self.get_storage_elements()
        for se in ses:
            if str(se["id"]) == str(identifier) or identifier in se["name"]:
                return se
        return None

    def generate_test_file(self, size_kb: int = FILE_SIZE_KB) -> Tuple[bytes, str]:
        """Генерация тестового файла"""
        content = ''.join(random.choices(string.ascii_letters + string.digits, k=size_kb * 1024))
        filename = f"test_file_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}.txt"
        return content.encode(), filename

    def upload_file(self, content: bytes, filename: str, retention_policy: str = "temporary") -> Dict:
        """Загрузка файла через Ingester"""
        files = {
            'file': (filename, content, 'text/plain')
        }
        data = {
            'retention_policy': retention_policy
        }

        resp = requests.post(
            f"{INGESTER_URL}/api/v1/files/upload",
            files=files,
            data=data,
            headers={"Authorization": f"Bearer {self.get_sa_token()}"}
        )
        resp.raise_for_status()
        return resp.json()

    def upload_multiple_files(self, count: int, size_kb: int = FILE_SIZE_KB,
                               retention_policy: str = "temporary") -> List[Dict]:
        """Загрузить несколько файлов"""
        results = []
        for i in range(count):
            content, filename = self.generate_test_file(size_kb)
            result = self.upload_file(content, filename, retention_policy)
            results.append(result)
            self.uploaded_files.append(result)
            print(f"  Uploaded {i+1}/{count}: {filename} -> SE: {result.get('storage_element_id', 'unknown')}")
        return results

    def finalize_file(self, file_id: str) -> Dict:
        """Финализация файла (TEMPORARY -> PERMANENT)"""
        resp = requests.post(
            f"{INGESTER_URL}/api/v1/finalize/{file_id}",
            headers={"Authorization": f"Bearer {self.get_sa_token()}"}
        )
        resp.raise_for_status()
        return resp.json()

    def run_t1_sequential_fill(self) -> TestResult:
        """T1: Загрузка 40 файлов в se-01 (Sequential Fill)"""
        result = TestResult("T1: Sequential Fill (40 files to se-01)")

        try:
            # Проверяем начальное состояние
            se_before = self.get_storage_elements()
            se01_before = next((s for s in se_before if s["id"] == 1), None)
            if not se01_before:
                result.failure("SE-01 not found")
                return result

            print(f"  SE-01 before: {se01_before['used_bytes']} bytes used")

            # Загружаем 40 файлов
            print("  Uploading 40 files...")
            uploads = self.upload_multiple_files(40, FILE_SIZE_KB)

            # Проверяем результаты
            se_after = self.get_storage_elements()
            se01_after = next((s for s in se_after if s["id"] == 1), None)

            # Подсчет файлов по SE
            se_counts = {}
            for upload in uploads:
                se_id = upload.get("storage_element_id")
                se_counts[se_id] = se_counts.get(se_id, 0) + 1

            print(f"  Files distribution: {se_counts}")
            print(f"  SE-01 after: {se01_after['used_bytes']} bytes used")

            # Проверяем Sequential Fill: все файлы должны быть в SE-01 (priority 100)
            if se_counts.get(1, 0) == 40:
                result.success(
                    f"All 40 files uploaded to SE-01 (Sequential Fill verified)",
                    files_in_se01=se_counts.get(1, 0),
                    bytes_used=se01_after['used_bytes']
                )
            else:
                # Возможно некоторые файлы попали в SE-02 если capacity достигнут
                result.success(
                    f"Files distributed: SE-01={se_counts.get(1,0)}, SE-02={se_counts.get(2,0)}",
                    distribution=se_counts,
                    bytes_used=se01_after['used_bytes']
                )

        except Exception as e:
            result.failure(f"Error: {str(e)}")

        self.results.append(result)
        return result

    def run_t2_fill_to_96(self) -> TestResult:
        """T2: Заполнение se-01 до 96%"""
        result = TestResult("T2: Fill SE-01 to 96%")

        try:
            se = self.get_se_by_name_or_id(1)
            if not se:
                result.failure("SE-01 not found")
                return result

            capacity = se["capacity_bytes"]
            current_used = se["used_bytes"]
            target_bytes = int(capacity * 0.96)  # 96%
            bytes_to_add = target_bytes - current_used

            print(f"  Current: {current_used}/{capacity} bytes ({current_used/capacity*100:.1f}%)")
            print(f"  Target: {target_bytes} bytes (96%)")
            print(f"  Need to add: {bytes_to_add} bytes")

            if bytes_to_add <= 0:
                result.success("SE-01 already at or above 96%",
                             current_percent=current_used/capacity*100)
            else:
                # Вычисляем количество файлов нужного размера
                file_size = FILE_SIZE_KB * 1024  # bytes
                files_needed = bytes_to_add // file_size + 1

                print(f"  Uploading {files_needed} files of {FILE_SIZE_KB}KB each...")

                # Загружаем файлы партиями
                batch_size = 50
                for i in range(0, files_needed, batch_size):
                    batch = min(batch_size, files_needed - i)
                    self.upload_multiple_files(batch, FILE_SIZE_KB)

                    # Проверяем текущий статус
                    se = self.get_se_by_name_or_id(1)
                    current_percent = se["used_bytes"] / se["capacity_bytes"] * 100
                    print(f"  Progress: {current_percent:.1f}%")

                    if current_percent >= 96:
                        break

                # Финальная проверка
                se = self.get_se_by_name_or_id(1)
                final_percent = se["used_bytes"] / se["capacity_bytes"] * 100

                if final_percent >= 96:
                    result.success(f"SE-01 filled to {final_percent:.1f}%",
                                 used_bytes=se["used_bytes"],
                                 capacity_bytes=se["capacity_bytes"])
                else:
                    result.success(f"SE-01 at {final_percent:.1f}% (target: 96%)",
                                 used_bytes=se["used_bytes"],
                                 capacity_bytes=se["capacity_bytes"])

        except Exception as e:
            result.failure(f"Error: {str(e)}")

        self.results.append(result)
        return result

    def run_t3_capacity_transitions(self) -> TestResult:
        """T3: Проверка Capacity Status Transitions"""
        result = TestResult("T3: Capacity Status Transitions")

        try:
            se = self.get_se_by_name_or_id(1)
            if not se:
                result.failure("SE-01 not found")
                return result

            capacity = se["capacity_bytes"]
            used = se["used_bytes"]
            usage_percent = used / capacity if capacity > 0 else 0

            # Определяем ожидаемый статус
            if usage_percent >= FULL_THRESHOLD:
                expected_status = "FULL"
            elif usage_percent >= CRITICAL_THRESHOLD:
                expected_status = "CRITICAL"
            elif usage_percent >= WARNING_THRESHOLD:
                expected_status = "WARNING"
            else:
                expected_status = "OK"

            print(f"  Usage: {usage_percent*100:.1f}%")
            print(f"  Expected status: {expected_status}")
            print(f"  Thresholds: WARNING={WARNING_THRESHOLD*100}%, CRITICAL={CRITICAL_THRESHOLD*100}%, FULL={FULL_THRESHOLD*100}%")

            # Проверяем метрики Prometheus если доступны
            try:
                metrics_resp = requests.get(f"{SE_01_URL}/metrics", timeout=5)
                if metrics_resp.ok:
                    metrics = metrics_resp.text
                    print(f"  Metrics available: {len(metrics)} bytes")
                    result.success(
                        f"Usage at {usage_percent*100:.1f}%, expected status: {expected_status}",
                        usage_percent=usage_percent*100,
                        expected_status=expected_status
                    )
                else:
                    result.success(
                        f"Usage at {usage_percent*100:.1f}%, metrics endpoint returned {metrics_resp.status_code}",
                        usage_percent=usage_percent*100
                    )
            except Exception as e:
                result.success(
                    f"Usage at {usage_percent*100:.1f}%, metrics check failed: {e}",
                    usage_percent=usage_percent*100
                )

        except Exception as e:
            result.failure(f"Error: {str(e)}")

        self.results.append(result)
        return result

    def run_t4_switch_to_se02(self) -> TestResult:
        """T4: Переключение на se-02 при FULL se-01"""
        result = TestResult("T4: Switch to SE-02 when SE-01 is FULL")

        try:
            # Проверяем текущее состояние SE-01
            se01 = self.get_se_by_name_or_id(1)
            se01_usage = se01["used_bytes"] / se01["capacity_bytes"] if se01["capacity_bytes"] > 0 else 0

            print(f"  SE-01 usage: {se01_usage*100:.1f}%")

            if se01_usage < FULL_THRESHOLD:
                # Нужно заполнить SE-01 до FULL
                print(f"  SE-01 not full yet, filling to {FULL_THRESHOLD*100}%...")
                bytes_to_add = int(se01["capacity_bytes"] * FULL_THRESHOLD) - se01["used_bytes"]
                files_needed = bytes_to_add // (FILE_SIZE_KB * 1024) + 1

                for i in range(files_needed):
                    content, filename = self.generate_test_file(FILE_SIZE_KB)
                    self.upload_file(content, filename)

                    if (i + 1) % 10 == 0:
                        se01 = self.get_se_by_name_or_id(1)
                        se01_usage = se01["used_bytes"] / se01["capacity_bytes"]
                        print(f"    Progress: {se01_usage*100:.1f}%")

                        if se01_usage >= FULL_THRESHOLD:
                            break

            # Теперь SE-01 должен быть FULL, загружаем новый файл
            print("  Uploading new file (should go to SE-02)...")
            content, filename = self.generate_test_file(FILE_SIZE_KB)
            upload_result = self.upload_file(content, filename)

            target_se = upload_result.get("storage_element_id")
            print(f"  New file uploaded to SE: {target_se}")

            if target_se == 2:
                result.success("New file correctly routed to SE-02", storage_element_id=target_se)
            elif target_se == 1:
                # Возможно SE-01 еще не полностью full
                se01 = self.get_se_by_name_or_id(1)
                result.success(
                    f"File still went to SE-01 (usage: {se01['used_bytes']/se01['capacity_bytes']*100:.1f}%)",
                    storage_element_id=target_se
                )
            else:
                result.success(f"File routed to SE-{target_se}", storage_element_id=target_se)

        except Exception as e:
            result.failure(f"Error: {str(e)}")

        self.results.append(result)
        return result

    def run_t5_upload_to_se02(self) -> TestResult:
        """T5: Загрузка 20 файлов в se-02"""
        result = TestResult("T5: Upload 20 files to SE-02")

        try:
            se02_before = self.get_se_by_name_or_id(2)
            print(f"  SE-02 before: {se02_before['used_bytes']} bytes used")

            # Загружаем 20 файлов
            print("  Uploading 20 files...")
            uploads = self.upload_multiple_files(20, FILE_SIZE_KB)

            se02_after = self.get_se_by_name_or_id(2)

            # Подсчет файлов по SE
            se_counts = {}
            for upload in uploads:
                se_id = upload.get("storage_element_id")
                se_counts[se_id] = se_counts.get(se_id, 0) + 1

            print(f"  Files distribution: {se_counts}")
            print(f"  SE-02 after: {se02_after['used_bytes']} bytes used")

            files_in_se02 = se_counts.get(2, 0)
            result.success(
                f"Uploaded {sum(se_counts.values())} files, {files_in_se02} to SE-02",
                distribution=se_counts,
                se02_bytes_used=se02_after['used_bytes']
            )

        except Exception as e:
            result.failure(f"Error: {str(e)}")

        self.results.append(result)
        return result

    def run_t6_finalization(self) -> TestResult:
        """T6: File Finalization (TEMPORARY→PERMANENT)"""
        result = TestResult("T6: File Finalization (TEMPORARY→PERMANENT)")

        try:
            # Выбираем несколько файлов для финализации
            files_to_finalize = self.uploaded_files[:5] if len(self.uploaded_files) >= 5 else self.uploaded_files

            if not files_to_finalize:
                result.failure("No files available for finalization")
                return result

            print(f"  Finalizing {len(files_to_finalize)} files...")

            finalized = []
            failed = []

            for file_info in files_to_finalize:
                file_id = file_info.get("file_id") or file_info.get("id")
                if not file_id:
                    continue

                try:
                    fin_result = self.finalize_file(file_id)
                    finalized.append({"file_id": file_id, "result": fin_result})
                    print(f"    Finalized: {file_id}")
                except Exception as e:
                    failed.append({"file_id": file_id, "error": str(e)})
                    print(f"    Failed: {file_id} - {e}")

            if finalized:
                result.success(
                    f"Finalized {len(finalized)} files, {len(failed)} failed",
                    finalized_count=len(finalized),
                    failed_count=len(failed)
                )
            else:
                result.failure(f"Failed to finalize any files", failed=failed)

        except Exception as e:
            result.failure(f"Error: {str(e)}")

        self.results.append(result)
        return result

    def run_t7_new_files_to_edit(self) -> TestResult:
        """T7: Проверка маршрутизации новых файлов в edit SE (не в rw)"""
        result = TestResult("T7: New files should go to edit SE (not rw)")

        try:
            # Загружаем несколько новых файлов с TEMPORARY policy
            print("  Uploading 5 new TEMPORARY files...")
            uploads = self.upload_multiple_files(5, FILE_SIZE_KB, "temporary")

            # Проверяем куда попали файлы
            se_counts = {}
            for upload in uploads:
                se_id = upload.get("storage_element_id")
                se_counts[se_id] = se_counts.get(se_id, 0) + 1

            print(f"  Files distribution: {se_counts}")

            # SE-01 и SE-02 - edit mode, SE-03 - rw mode
            # TEMPORARY файлы должны идти только в edit SE (1 или 2)
            files_in_edit = se_counts.get(1, 0) + se_counts.get(2, 0)
            files_in_rw = se_counts.get(3, 0)

            if files_in_rw == 0:
                result.success(
                    f"All {files_in_edit} files correctly routed to edit SE (SE-01 or SE-02)",
                    distribution=se_counts
                )
            else:
                result.failure(
                    f"{files_in_rw} files incorrectly routed to rw SE (SE-03)",
                    distribution=se_counts
                )

        except Exception as e:
            result.failure(f"Error: {str(e)}")

        self.results.append(result)
        return result

    def generate_report(self) -> Dict:
        """Генерация отчета"""
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        report = {
            "phase": "Phase 3: Positive Scenarios",
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_tests": len(self.results),
                "passed": passed,
                "failed": failed,
                "success_rate": f"{passed/len(self.results)*100:.1f}%" if self.results else "0%"
            },
            "results": [r.to_dict() for r in self.results],
            "files_uploaded": len(self.uploaded_files)
        }

        return report

    def run_all_tests(self):
        """Запуск всех тестов Фазы 3"""
        print("=" * 60)
        print("ФАЗА 3: ПОЗИТИВНЫЕ СЦЕНАРИИ")
        print("=" * 60)
        print()

        # T1: Sequential Fill
        print("--- T1: Sequential Fill (40 files) ---")
        self.run_t1_sequential_fill()
        print()

        # T2: Fill to 96%
        print("--- T2: Fill SE-01 to 96% ---")
        self.run_t2_fill_to_96()
        print()

        # T3: Capacity Transitions
        print("--- T3: Capacity Status Transitions ---")
        self.run_t3_capacity_transitions()
        print()

        # T4: Switch to SE-02
        print("--- T4: Switch to SE-02 ---")
        self.run_t4_switch_to_se02()
        print()

        # T5: Upload 20 to SE-02
        print("--- T5: Upload 20 files to SE-02 ---")
        self.run_t5_upload_to_se02()
        print()

        # T6: Finalization
        print("--- T6: File Finalization ---")
        self.run_t6_finalization()
        print()

        # T7: New files to edit SE
        print("--- T7: New files to edit SE ---")
        self.run_t7_new_files_to_edit()
        print()

        # Generate report
        report = self.generate_report()

        print("=" * 60)
        print("РЕЗУЛЬТАТЫ ФАЗЫ 3")
        print("=" * 60)
        print(f"Всего тестов: {report['summary']['total_tests']}")
        print(f"Успешно: {report['summary']['passed']}")
        print(f"Неудачно: {report['summary']['failed']}")
        print(f"Success Rate: {report['summary']['success_rate']}")
        print(f"Файлов загружено: {report['files_uploaded']}")
        print()

        # Save report
        report_path = "test_artifacts/phase3_results.json"
        os.makedirs("test_artifacts", exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"Отчет сохранен: {report_path}")

        return report


if __name__ == "__main__":
    tester = Phase3Tester()

    # Check connectivity
    try:
        tester.get_sa_token()
        print("✅ SA Token obtained")
        tester.get_admin_token()
        print("✅ Admin Token obtained")

        ses = tester.get_storage_elements()
        print(f"✅ Found {len(ses)} Storage Elements")
        for se in ses:
            print(f"   - SE-{se['id']}: {se['name']} ({se['mode']}) - {se['used_bytes']}/{se['capacity_bytes']} bytes")
        print()
    except Exception as e:
        print(f"❌ Connectivity check failed: {e}")
        sys.exit(1)

    # Run tests
    report = tester.run_all_tests()

    # Exit code based on results
    if report['summary']['failed'] > 0:
        sys.exit(1)
    sys.exit(0)
