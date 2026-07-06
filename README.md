# PPT-Agent (Autonomous Business Intelligence Presentation System)

An intelligent business research and presentation generation system that automatically researches a company, extracts key business insights, saves information in MongoDB, and designs professional PowerPoint presentations.

## Project Structure

This project is divided into modular packages so multiple team members can work in parallel:

*   **`linkedin/`**: Scraping and data collection from LinkedIn profiles.
*   **`website/`**: Crawling and parsing the target company's website.
*   **`google_search/`**: Gathering search engine results, news, and competitors.
*   **`config/`**: Global configuration loader (`settings.py`) using `.env`.
*   **`utils/`**: Common utility modules, including the shared MongoDB connection helper (`db_client.py`).
*   **`pipeline/`**: Logic to validate and normalize raw company information.
*   **`bi_extraction/`**: Extracting high-level insights (opportunities, challenges, differentiators).
*   **`planner/`**: Deconstructing business intelligence into slide narratives.
*   **`generator/`**: Creating and styling PPTX presentations.
*   **`data/`** (gitignored): Storage for raw and processed test data.

## Getting Started

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/dhiraj-rajput/PPT-Agent.git
    cd PPT-Agent
    ```

2.  **Set up environment variables:**
    *   Copy `.env.example` to `.env`.
    *   Configure your MongoDB connection string and relevant API keys in `.env`.

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
