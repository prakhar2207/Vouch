# Vouch ⚡

> **High-Speed Double-Entry Accounting & AI ERP for Modern Businesses**

Vouch is a keyboard-first, cloud-native ERP platform built for rapid business operations, automated GST compliance, and AI-powered accounts payable invoice extraction.

---

## 🌟 Key Features

- **⚡ 100% Keyboard-First Workflow**: Standard F4–F9 shortcuts, \Alt+C\ for on-the-fly master creation, \Ctrl+A\ instant posting, and \Ctrl+K\ global command palette.
- **🤖 AI Bill Scanner (F9)**: Drag-and-drop or upload PDF/photo supplier bills. AI extracts line items, validates HSN codes, verifies GSTIN, and auto-populates vouchers with split-screen review.
- **🧾 Flawless GST Compliance**: Automatic computation of CGST, SGST, and IGST based on 2-digit state codes, real-time inventory deductions, and audit-proof double-entry balancing.
- **📊 High-Density AG Grid**: Spreadsheet-grade grid data entry with keyboard navigation (Tab/Enter/Arrows) and live debit/credit balancing.
- **📈 Business Health & Insights**: RFM customer value clustering and revenue trend forecasting.
- **📱 PWA & Offline Support**: Progressive Web App with offline caching and installable desktop/mobile experience.

---

## 🏗️ Architecture & Tech Stack

- **Frontend**: Next.js 16 (Turbopack, App Router), React 19, Tailwind CSS v4, AG Grid, Recharts, Framer Motion, Serwist PWA
- **Backend**: Django 6.1, Django REST Framework, SimpleJWT Authentication, Celery, Google GenAI SDK
- **Database & Cache**: PostgreSQL 15, Redis 7

---

## 🚀 Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/)
- [Python 3.11+](https://www.python.org/)
- [Node.js 18+](https://nodejs.org/) & npm

---

### 1. Clone & Set Up Environment

\\\ash
git clone https://github.com/prakhar2207/Vouch.git
cd Vouch
cp .env.example .env
\\\

### 2. Start PostgreSQL & Redis with Docker

\\\ash
docker compose up -d
\\\

### 3. Backend Setup (Django)

\\\ash
# Create & activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
# source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start backend development server
python manage.py runserver 0.0.0.0:8000
\\\

### 4. Frontend Setup (Next.js)

\\\ash
cd frontend
npm install
npm run dev
\\\

The application will be running at:
- **Frontend Web App**: http://localhost:3000
- **Backend API & Admin**: http://localhost:8000

---

## ⌨️ Essential Keyboard Shortcuts

| Key | Action | Description |
| :--- | :--- | :--- |
| \F1\ | Help & Guide | Open shortcuts reference & tutorial |
| \F2\ | Change Date | Adjust current working date period |
| \F4\ | Contra Voucher | Bank & cash transfers |
| \F5\ | Payment Voucher | Supplier payments & expenses |
| \F6\ | Receipt Voucher | Customer receipt entries |
| \F7\ | Journal Voucher | Adjustments & journal entries |
| \F8\ | Sales Invoice | Customer GST billing |
| \F9\ | Purchase Invoice | Vendor bill entry & AI Scanner |
| \Ctrl + K\ | Command Palette | Instant search across accounts & items |
| \Ctrl + A\ | Accept / Save | Post active voucher immediately |
| \Alt + C\ | Create Master | Create Party / Item on the fly inside form |
| \Alt + P\ | Print Preview | Generate GST invoice preview |

---

## 📄 License

Proprietary. All rights reserved.
