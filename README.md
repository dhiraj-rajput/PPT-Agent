# OrbitAvanya (formerly PPT-Agent)

OrbitAvanya is a complete, multi-tenant-shaped SaaS application and intelligence pipeline for tender discovery, company profiling, CRM, and proposal automation. It builds on top of an autonomous business research engine that scrapes and structures data from LinkedIn, company websites, and search engines, offering automated RFP analysis and proposal drafting.

## System Architecture

The project is structured into three primary layers:
1. **Frontend**: React 18 + Vite SPA styled with Tailwind CSS (`frontend/`).
2. **Backend API**: FastAPI backend routing auth, CRM users, tasks, meetings, notifications, integrations, SAM.gov opportunities, and proposal documents (`api/`, `server.py`).
3. **Research Pipeline**: Modular agents for data collection and insight extraction:
   * **`linkedin/`**: Public and authenticated LinkedIn crawler.
   * **`website/`**: Crawling and cleaning website pages using crawl4ai & Playwright.
   * **`google_search/`**: Competitor intelligence and Google search wrapper.
   * **`orchestrator/`**: LangGraph-based state machine coordinating agents.
   * **`models/`**: Data normalizers and LLM-based compaction layer.
   * **`bidforge/`**: Cold-upload document ingestion and RFP auto-response.
   * **`utils/`**: Shared MongoDB client (`db_client.py`), docx/pdf generation helpers, and proposal engines.
4. **CLI Tools & Utility Scripts**: Consolidated in `scripts/`:
   * **`scripts/search_rfps.py`**: Search opportunities on SAM.gov.
   * **`scripts/respond_to_rfp.py`**: Respond to solicitation numbers.
   * **`scripts/bidforge_cli.py`**: Cold-upload RFP PDF analysis.
   * **`scripts/parse_sam.py`**: One-off local entity database loader.

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js & Bun / npm
- MongoDB instance (Local or Atlas)
- Tesseract OCR (for scanned PDF processing)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/dhiraj-rajput/PPT-Agent.git
   cd PPT-Agent
   ```

2. **Configure Environment:**
   Copy `.env.example` to `.env` and fill in:
   - `MONGO_URI` & `MONGO_DB_NAME`
   - `JWT_SECRET` (Run `openssl rand -hex 32` to generate a strong key)
   - `TAVILY_API_KEY` (For web/company search)
   - `OLLAMA_MODEL` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY` (AI model credentials)

3. **Install Backend Dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Install Frontend Dependencies:**
   ```bash
   cd frontend
   bun install  # or npm install
   ```

### Running Locally

- **Start MongoDB:** Ensure MongoDB is running on your configured URI.
- **Start FastAPI Backend:**
   ```bash
   python server.py
   ```
- **Start React Frontend:**
   ```bash
   cd frontend
   bun dev  # or npm run dev
   ```
