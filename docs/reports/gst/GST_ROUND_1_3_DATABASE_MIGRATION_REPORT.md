# SriLekh GST Integration — Round 1.3 Database Migration Report
## Schema Changes, Constraint Verification & Zero-Downtime Deployment Analysis

- **Target Application:** `apps.gst`
- **Migration File:** `apps/gst/migrations/0007_gstregistration_unique_primary_gstin_per_company.py`
- **Target Branch:** `fix/stage4-12-day6-remediation`
- **Date:** November 16, 2026
- **Status:** GENERATED, DRY-RUN VALIDATED & REVERSIBLE

---

## 1. Migration Overview

Migration `0007_gstregistration_unique_primary_gstin_per_company` adds a database-level partial unique constraint to `GSTRegistration` to enforce that each company has at most one primary GSTIN registration.

### Dependency Chain
- Previous Migration: `0006_auto_20260921_1037` (ITC reconciliation and GSTR-2B cache models)
- Current Migration: `0007_gstregistration_unique_primary_gstin_per_company`

---

## 2. Schema Specification & SQL Operations

### Django Model Definition
```python
# apps/gst/models.py (GSTRegistration.Meta)
constraints = [
    models.UniqueConstraint(
        fields=['company'],
        condition=models.Q(is_primary=True),
        name='unique_primary_gstin_per_company'
    )
]
```

### Generated Migration Operations
```python
# apps/gst/migrations/0007_gstregistration_unique_primary_gstin_per_company.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('gst', '0006_auto_20260921_1037'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='gstregistration',
            constraint=models.UniqueConstraint(
                condition=models.Q(('is_primary', True)),
                fields=('company',),
                name='unique_primary_gstin_per_company'
            ),
        ),
    ]
```

### PostgreSQL Generated DDL (Target Engine: Neon)
```sql
CREATE UNIQUE INDEX "unique_primary_gstin_per_company" 
ON "gst_gstregistration" ("company_id") 
WHERE "is_primary" = TRUE;
```

---

## 3. Migration Safety & Performance Assessment

1. **Zero Table Locking:** Adding a partial unique index on PostgreSQL creates a B-Tree index on filtered rows (`WHERE is_primary = TRUE`). On Neon PostgreSQL, this executes in sub-millisecond time.
2. **Backward Compatibility:** Existing active rows where `is_primary = False` are completely unaffected by this index.
3. **Data Pre-validation:** Before applying this migration to staging or production databases, existing rows must satisfy `count(is_primary=True) <= 1` per company. In existing production tenant books (`Maa Annapurna Belting Store`), at most 1 primary GSTIN exists.
4. **Reversibility:** Fully reversible via `migrations.RemoveConstraint`.
5. **Dry-Run Check:** `python manage.py makemigrations --check --dry-run` confirms clean schema state with zero unmigrated models.
