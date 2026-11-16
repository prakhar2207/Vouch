<div align="center">
  <img src="assets/branding/ShriLekh-final-logo-HD-2400.png" alt="SriLekh Logo" width="260" />
  <h1>SriLekh (श्रीलेख) ⚡</h1>
  <p><strong>High-Speed Double-Entry Accounting, Automated GST Compliance & AI ERP for Modern Indian Businesses</strong></p>

  <p>
    <a href="https://srilekh.com"><img src="https://img.shields.io/badge/Production-srilekh.com-2563eb?style=flat-square&logo=googlechrome&logoColor=white" alt="Live Site" /></a>
    <img src="https://img.shields.io/badge/Frontend-Next.js%2016-black?style=flat-square&logo=next.js" alt="Next.js 16" />
    <img src="https://img.shields.io/badge/Backend-Django%206-092e20?style=flat-square&logo=django" alt="Django 6" />
    <img src="https://img.shields.io/badge/Language-TypeScript%20%7C%20Python-3178c6?style=flat-square&logo=typescript" alt="TypeScript / Python" />
    <img src="https://img.shields.io/badge/Mobile-Android%20%28.aab%29%20%26%20PWA-34d399?style=flat-square&logo=android" alt="Android & PWA" />
    <img src="https://img.shields.io/badge/Database-PostgreSQL%2015-336791?style=flat-square&logo=postgresql" alt="PostgreSQL" />
    <img src="https://img.shields.io/badge/License-Proprietary-red?style=flat-square" alt="License" />
  </p>
</div>

---

## 🌟 Overview

**SriLekh** (formerly Vouch) is an enterprise-grade, keyboard-first ERP platform engineered specifically for Indian MSMEs, distributors, wholesalers, and retail businesses. It blends Tally-level keyboard speed with cloud-native reliability, automated GST compliance, and Google Gemini multimodal AI invoice extraction.

### 🔗 Public & Production Links
* **Official Website**: [https://srilekh.com](https://srilekh.com)
* **Pricing & Plans**: [https://srilekh.com/pricing](https://srilekh.com/pricing)
* **Refund & Cancellation Policy**: [https://srilekh.com/refund-policy](https://srilekh.com/refund-policy)
* **Privacy Policy**: [https://srilekh.com/privacy-policy](https://srilekh.com/privacy-policy)
* **Terms of Service**: [https://srilekh.com/terms](https://srilekh.com/terms)

---

## 🚀 Key Features

* **⚡ 100% Keyboard-First Workflow**: Standard `F4`–`F9` accounting shortcuts, `Alt+C` on-the-fly master creation, `Ctrl+A` instant voucher posting, and `Ctrl+K` global command palette.
* **🤖 AI Bill Scanner (F9)**: Drag-and-drop or photograph vendor bills. Gemini AI extracts line items, validates HSN codes, verifies GSTIN, and auto-populates vouchers with split-screen review.
* **🧾 Indian GST Compliance**: Automatic computation of CGST, SGST, and IGST based on 2-digit state codes, multi-GSTIN branch support, and GSTR-2B ITC Shield invoice reconciliation.
* **🏦 Automated 4-Pass Bank Reconciliation**: Ingest Excel/CSV statements, automatically detect and link contra vouchers, and reconcile ledger entries with zero human error.
* **🌐 B2B Network Inward Ingestion**: Cross-tenant invoice dispatching. Invoices sent by suppliers arrive directly in the recipient's `/network/inbox` for 1-click acceptance.
* **📱 Offline-First PWA & Native Android**: AES-GCM encrypted IndexedDB offline cache, background outbox worker, and downloadable Android App Bundle (`.aab`) & APK.
* **📈 Predictive Analytics**: RFM customer value clustering, revenue trend forecasting, 80-20 Pareto analysis, and Cash Conversion Cycle metrics.

---

## 🏗️ Architecture & Tech Stack

```
                        ┌──────────────────────────────────────────────┐
                        │              Client Layer                    │
                        │  Next.js 16 (App Router) • Capacitor Android │
                        │   Tailwind CSS • AG Grid • Serwist PWA       │
                        └──────────────────────┬───────────────────────┘
                                               │ HTTPS / REST / WSS
                                               ▼
                        ┌──────────────────────────────────────────────┐
                        │            API & Application Server          │
                        │       Django 6.1 • Django REST Framework    │
                        │     SimpleJWT Auth • Gemini GenAI SDK        │
                        └──────────────┬───────────────┬───────────────┘
                                       │               │
                        ┌──────────────▼──────┐ ┌──────▼───────────────┐
                        │   PostgreSQL 15     │ │  Redis 7 & Celery    │
                        │ (Double-Entry Core) │ │ (Outbox / Background)│
                        └─────────────────────┘ └──────────────────────┘
```

| Component | Technologies |
| :--- | :--- |
| **Frontend** | Next.js 16, React 19, Tailwind CSS v4, AG Grid Enterprise, Recharts, Framer Motion, Serwist PWA |
| **Mobile** | Capacitor 7 (Android App Bundle `.aab`, Debug `.apk`, iOS Xcode Workspace) |
| **Backend** | Django 6.1, Django REST Framework, SimpleJWT, Celery, Google GenAI SDK |
| **Database & Cache** | PostgreSQL 15, Redis 7 (Outbox worker & token store) |
| **Security & Privacy** | AES-GCM client-side encryption, DPDP Act 2023 compliance, SHA-256 audit chaining |

---

## 📂 Repository Layout

```
├── .github/              # CI/CD Workflows (Play Store .aab, Vercel deployments, test suites)
├── apps/                 # Django Apps (accounting, companies, gst, inventory, ledgers, etc.)
├── assets/               # Brand assets, high-resolution logos, and icons
├── config/               # Django root settings, URLs, and Celery configuration
├── docs/                 # Architecture designs, security audits, EDI specs, and stage reports
│   ├── architecture/     # System scaling and UI responsiveness blueprints
│   ├── audits/           # Security, penetration testing, and regression audits
│   ├── compliance/       # DPDP Act, GST, and legal documentation
│   ├── edi/              # B2B network protocol specifications
│   ├── play-store/       # Mobile release reports and submission checklists
│   └── reports/          # Milestone execution reports (Stage 1, Stage 4, GST)
├── frontend/             # Next.js 16 Web Application & Capacitor Mobile Shell
├── scripts/              # Operational utilities, icon generation, and build scripts
└── vouch-protocol-poc/   # Cryptographic B2B EDI protocol proof-of-concept
```

---

## 🚀 Getting Started

### Prerequisites
* [Docker Desktop](https://www.docker.com/)
* [Python 3.11+](https://www.python.org/)
* [Node.js 20+](https://nodejs.org/) & npm

### 1. Clone & Setup Environment
```bash
git clone https://github.com/prakhar2207/Vouch.git
cd Vouch
cp .env.example .env
```

### 2. Start PostgreSQL & Redis
```bash
docker compose up -d
```

### 3. Backend Setup (Django)
```bash
# Create & activate virtual environment
python -m venv venv

# Windows:
.\venv\Scripts\activate
# Linux/macOS:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
python manage.py migrate

# Start backend server
python manage.py runserver 0.0.0.0:8000
```

### 4. Frontend Setup (Next.js)
```bash
cd frontend
npm install
npm run dev
```

* **Frontend**: [http://localhost:3000](http://localhost:3000)
* **Backend API & Admin**: [http://localhost:8000](http://localhost:8000)

---

## ⌨️ Essential Keyboard Shortcuts

| Shortcut | Action | Description |
| :--- | :--- | :--- |
| `F1` | Help & Guide | Open keyboard shortcut reference & tutorial |
| `F2` | Change Date | Adjust current accounting date |
| `F4` | Contra Voucher | Cash deposits, withdrawals, and bank-to-bank transfers |
| `F5` | Payment Voucher | Supplier payments, operational expenses |
| `F6` | Receipt Voucher | Customer collections and receipt entries |
| `F7` | Journal Voucher | Year-end adjustments and non-cash journal entries |
| `F8` | Sales Invoice | GST billing with 1-click PDF & WhatsApp sharing |
| `F9` | Purchase Invoice | Vendor bill entry & AI Scanner split-screen extraction |
| `Ctrl + K` | Command Palette | Global navigation across all ledgers, items, and settings |
| `Ctrl + A` | Save / Accept | Instant voucher posting with double-entry validation |
| `Alt + C` | Create Master | Create new customer, supplier, or product on the fly |

---

## 🛡️ Core Accounting Invariants

1. **Mathematical Equilibrium**: Every posted transaction strictly enforces $\sum \text{Debits} == \sum \text{Credits}$.
2. **Double-Entry Integrity**: Unlinked or orphaned ledger entries are mathematically impossible at the database constraint level.
3. **Tenant & Data Isolation**: Tenant boundaries are enforced through strict schema-level query scoping; cross-tenant leakage fails closed.
4. **Tamper-Evident Audit Trail**: All accounting mutations maintain cryptographic SHA-256 hash chains for audit readiness.

---

## 📄 License & Contact

* **License**: Proprietary — All Rights Reserved.
* **Support & Contact**: [admin@srilekh.com](mailto:admin@srilekh.com)
* **Headquarters**: Kanpur, Uttar Pradesh, India
