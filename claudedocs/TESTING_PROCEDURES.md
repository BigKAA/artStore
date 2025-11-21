# ArtStore Testing Procedures

## E2E Testing Strategy

### Test Categories

1. **Authentication & Authorization Tests**
2. **File Manager Integration Tests**
3. **Admin User Management Tests**
4. **Service Account Management Tests**
5. **Storage Element Management Tests**

## File Manager E2E Tests

### Prerequisites

```bash
# Ensure all services are running
docker ps | grep -E "admin_module|query_module|ingester_module|postgres|redis"

# Ensure Admin UI is running
curl http://localhost:4200

# Verify database tables exist
docker exec artstore_postgres psql -U artstore -d artstore -c "\dt file_metadata_cache"
```

### Test Scenarios

#### 1. File Manager Page Load Test

**Objective**: Verify File Manager loads without errors

**Steps**:
1. Navigate to http://localhost:4200/files
2. Verify authentication (should be logged in as admin)
3. Check page elements:
   - Header "Управление файлами"
   - File counter "Всего файлов: 0"
   - Upload button "Загрузить файл"
   - Search form with filters
   - File table with headers
4. Verify no console errors
5. Verify Query Module connection (port 8030)

**Expected Result**: Page loads successfully with empty file list

**Playwright Test**:
```typescript
test('File Manager loads successfully', async ({ page }) => {
  await page.goto('http://localhost:4200/files');

  // Verify page loaded
  await expect(page).toHaveTitle('Files - ArtStore Admin');

  // Verify header
  await expect(page.getByRole('heading', { name: 'Управление файлами' })).toBeVisible();

  // Verify upload button
  await expect(page.getByRole('button', { name: 'Загрузить файл' })).toBeVisible();

  // Verify table
  await expect(page.getByRole('table')).toBeVisible();

  // Verify file counter
  await expect(page.getByText('Всего файлов: 0')).toBeVisible();
});
```

#### 2. File Upload Test

**Objective**: Upload file through Admin UI

**Steps**:
1. Click "Загрузить файл" button
2. Upload modal opens
3. Select test file (e.g., `test_document.pdf`)
4. Add description: "Test file upload"
5. Click "Загрузить" button
6. Wait for upload progress
7. Verify success message
8. Verify file appears in table

**Prerequisites**:
- Ingester Module running (port 8020)
- Storage Element available and accessible
- Test file prepared: `/tmp/test_document.pdf`

**Playwright Test**:
```typescript
test('Upload file successfully', async ({ page }) => {
  await page.goto('http://localhost:4200/files');

  // Open upload modal
  await page.getByRole('button', { name: 'Загрузить файл' }).click();

  // Fill form
  await page.setInputFiles('input[type="file"]', '/tmp/test_document.pdf');
  await page.fill('textarea[placeholder*="Описание"]', 'Test file upload');

  // Submit
  await page.getByRole('button', { name: 'Загрузить' }).click();

  // Wait for success
  await expect(page.getByText(/успешно загружен/)).toBeVisible({ timeout: 10000 });

  // Verify file in table
  await expect(page.getByText('test_document.pdf')).toBeVisible();
});
```

#### 3. File Search Test

**Objective**: Search and filter files

**Steps**:
1. Enter search query: "test"
2. Click "Поиск" button
3. Verify results filtered
4. Select file type filter: "PDF"
5. Click "Применить фильтры"
6. Verify results match filters
7. Click "Сбросить"
8. Verify all files shown

**Playwright Test**:
```typescript
test('Search and filter files', async ({ page }) => {
  await page.goto('http://localhost:4200/files');

  // Assume file already uploaded
  const searchInput = page.getByPlaceholder(/Поиск по имени файла/);
  await searchInput.fill('test');
  await page.getByRole('button', { name: 'Поиск' }).click();

  // Verify search results
  await expect(page.getByText('test_document.pdf')).toBeVisible();

  // Apply filter
  await page.selectOption('select', { label: 'PDF' });
  await page.getByRole('button', { name: 'Применить фильтры' }).click();

  // Verify filtered
  await expect(page.getByText('test_document.pdf')).toBeVisible();

  // Reset
  await page.getByRole('button', { name: 'Сбросить' }).click();

  // Verify all shown
  await expect(page.getByRole('table')).toBeVisible();
});
```

#### 4. File Download Test

**Objective**: Download file from Admin UI

**Steps**:
1. Locate file in table
2. Click "Скачать" button
3. Wait for download
4. Verify browser download triggered
5. Verify file downloaded correctly

**Playwright Test**:
```typescript
test('Download file successfully', async ({ page }) => {
  await page.goto('http://localhost:4200/files');

  // Setup download listener
  const downloadPromise = page.waitForEvent('download');

  // Click download button
  await page.getByRole('button', { name: 'Скачать' }).first().click();

  // Wait for download
  const download = await downloadPromise;

  // Verify filename
  expect(download.suggestedFilename()).toBe('test_document.pdf');

  // Save file
  await download.saveAs('/tmp/downloaded_test.pdf');

  // Verify file exists
  const fs = require('fs');
  expect(fs.existsSync('/tmp/downloaded_test.pdf')).toBe(true);
});
```

## Admin User Management Tests

### Test: Create Admin User

**Covered in Sprint 20 testing** ✅

**Result**: Successfully created user "artur" with Admin role

**Issues Found and Fixed**:
1. 307 Redirect issue - Fixed by adding trailing slashes
2. Context manager TypeError - Fixed by adding @contextmanager decorator

### Test: Admin User List

**Status**: ✅ Working

**Verification**:
```bash
curl -X GET http://localhost:8000/api/v1/admin-users/ \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

## Integration Test Structure

```
tests/
├── e2e/
│   ├── auth/
│   │   ├── test_login.spec.ts
│   │   └── test_jwt_validation.spec.ts
│   ├── files/
│   │   ├── test_file_manager_load.spec.ts
│   │   ├── test_file_upload.spec.ts
│   │   ├── test_file_search.spec.ts
│   │   └── test_file_download.spec.ts
│   ├── admin_users/
│   │   ├── test_user_crud.spec.ts
│   │   └── test_password_reset.spec.ts
│   └── service_accounts/
│       └── test_account_management.spec.ts
└── integration/
    ├── test_query_module_api.py
    ├── test_ingester_module_api.py
    └── test_admin_module_api.py
```

## Running Tests

### Playwright E2E Tests

```bash
# Install Playwright
cd admin-ui
npm install -D @playwright/test

# Run tests
npx playwright test

# Run specific test
npx playwright test tests/e2e/files/test_file_manager_load.spec.ts

# Debug mode
npx playwright test --debug

# UI mode
npx playwright test --ui
```

### Python Integration Tests

```bash
# Query Module
cd query-module
source /home/artur/Projects/artStore/.venv/bin/activate
pytest tests/integration/ -v

# Ingester Module
cd ingester-module
pytest tests/integration/ -v

# Admin Module
cd admin-module
pytest tests/integration/ -v
```

## Test Coverage Goals

### Current Status (Sprint 20)

- ✅ Admin User Management: CRUD operations tested
- ✅ File Manager Page Load: Verified working
- ✅ Query Module API: Database integration tested
- ✅ Authentication: JWT validation working
- ⏳ File Upload: Ready for testing (Ingester needs to be running)
- ⏳ File Download: Ready for testing
- ⏳ File Search: Basic search tested, full-text search pending

### Target Coverage

- **Unit Tests**: >80% coverage per module
- **Integration Tests**: All API endpoints covered
- **E2E Tests**: All critical user flows covered
- **Performance Tests**: Load testing for file operations

## Test Data Management

### Creating Test Files

```bash
# Create test PDF
echo "Test document content" > /tmp/test_document.txt
# Convert to PDF if needed or use existing PDF

# Create test images
convert -size 100x100 xc:blue /tmp/test_image.jpg

# Create test archive
tar -czf /tmp/test_archive.tar.gz /tmp/test_document.txt
```

### Cleanup After Tests

```bash
# Clean test files from database
docker exec artstore_postgres psql -U artstore -d artstore -c "DELETE FROM file_metadata_cache WHERE filename LIKE 'test_%';"

# Clean test files from storage
# (will depend on Storage Element configuration)
```

## Continuous Integration

### GitHub Actions Workflow (Example)

```yaml
name: E2E Tests

on: [push, pull_request]

jobs:
  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Start services
        run: docker-compose up -d

      - name: Wait for services
        run: |
          sleep 30
          curl --retry 10 --retry-delay 5 http://localhost:8000/health/live
          curl --retry 10 --retry-delay 5 http://localhost:8030/health/live

      - name: Run E2E tests
        run: |
          cd admin-ui
          npm install
          npx playwright install
          npx playwright test

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: playwright-report
          path: admin-ui/playwright-report/
```

## Known Issues & Workarounds

### Issue: File Upload Timeout

**Symptom**: Large file uploads timeout

**Workaround**: Increase timeout in Ingester Module nginx/uvicorn config

### Issue: Search Returns Empty Results

**Symptom**: Search query returns no results despite files existing

**Debug Steps**:
1. Check Query Module logs
2. Verify file_metadata_cache table populated
3. Check search_vector column generated
4. Verify PostgreSQL GIN indexes exist

### Issue: Download Fails with 404

**Symptom**: Download request returns 404

**Debug Steps**:
1. Verify file exists in Storage Element
2. Check storage_element_url in file_metadata_cache
3. Verify Storage Element is accessible from Query Module
4. Check Storage Element logs

## Test Reporting

After each test run, generate report:

```bash
# Playwright HTML report
npx playwright show-report

# Pytest coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html
```
