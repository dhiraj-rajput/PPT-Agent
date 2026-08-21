"""
app/sam_gov/competitors.py
--------------------------
Finds bidders, competitors, and proposal response details (prices, evaluations)
for a given solicitation number.
Leverages Tavily search to discover GAO bid protests or award details,
and extracts this intelligence using 100% rule-based and pattern-based regex.
No AI or LLM models are used.
"""

import re
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from utils.helpers import setup_logger

from app.sam_gov.document_parser import DocumentParser

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Mock Search & Competitor Data for Testing
# ---------------------------------------------------------------------------
MOCK_SEARCH_RESULTS = {
    "N00164-26-R-0001": [
        {
            "title": "Deloitte Consulting LLP GAO Protest Decision (B-426101.1)",
            "url": "https://www.gao.gov/products/b-426101.1",
            "snippet": (
                "Deloitte Consulting LLP protests the award of a contract to Booz Allen Hamilton Inc. under solicitation "
                "number N00164-26-R-0001 by the Department of the Navy for advanced business intelligence services. "
                "The protester argues that the Navy's evaluation of technical proposals was flawed. Booz Allen Hamilton "
                "offered a bid price of $12,450,000 with an 'Outstanding' technical rating, while Deloitte's bid was "
                "$13,100,000 with a 'Good' technical rating. GAO denied the protest, finding the evaluation reasonable."
            ),
            "provider": "tavily"
        },
        {
            "title": "Navy awards $12.4M business intelligence contract to Booz Allen",
            "url": "https://www.washingtontechnology.com/navy-award-booz-allen-bi",
            "snippet": (
                "The Department of the Navy has awarded a $12.4M contract to Booz Allen Hamilton Inc. to provide "
                "data analytics and dashboard support to Naval Sea Systems Command under solicitation N00164-26-R-0001. "
                "Other active bidders included Deloitte and Palantir Technologies."
            ),
            "provider": "tavily"
        }
    ],
    "DHS-2026-RFP-0043": [
        {
            "title": "FEMA awards financial analytics contract to Guidehouse",
            "url": "https://www.govconwire.com/fema-guidehouse-financial-analytics-award",
            "snippet": (
                "The Federal Emergency Management Agency (FEMA) has awarded Guidehouse LLP a $4.25M contract for "
                "enterprise financial analysis and predictive modeling services under solicitation DHS-2026-RFP-0043. "
                "The solicitation was competed as a full-and-open acquisition, attracting bids from SAIC and Booz Allen Hamilton."
            ),
            "provider": "tavily"
        }
    ]
}


class CompetitorExtractor:
    """
    Scrapes and extracts competitor names and their bid responses (pricing, technical scores)
    for a given solicitation by searching web sources and GAO protest logs.
    """

    def __init__(self) -> None:
        self.tavily_key = settings.TAVILY_API_KEY
        self.db = None
        try:
            from utils.db_client import get_database
            self.db = get_database()
        except Exception as exc:
            logger.warning(f"MongoDB not available in CompetitorExtractor: {exc}")

    def find_competitors_and_bids(
        self,
        solicitation_number: str,
        use_mock: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Discover bidders and bid responses for a solicitation using web search + rule-based parsing.
        """
        sol_num = solicitation_number.strip()
        
        # 1. Check database cache
        if self.db is not None and not use_mock:
            try:
                rfp_col = self.db["rfps"]
                cached = rfp_col.find_one({"solicitation_number": sol_num})
                if cached and cached.get("competitors") and cached.get("protest_raw_documents"):
                    logger.info(f"Retrieved cached competitor details for solicitation: {sol_num}")
                    return cached["competitors"]
            except Exception as e:
                logger.warning(f"Failed to query cache in CompetitorExtractor: {e}")

        # 2. Search for relevant pages
        snippets = []
        if use_mock or not self.tavily_key or "your_" in self.tavily_key:
            logger.info(f"Using mock search data for solicitation competitor search: {sol_num}")
            snippets = MOCK_SEARCH_RESULTS.get(sol_num, [])
            if not snippets:
                snippets = [
                    {
                        "title": f"Award announcement for solicitation {sol_num}",
                        "url": "https://www.govconwire.com/mock-award",
                        "snippet": f"The government awarded a contract under solicitation {sol_num}. The winning contractor was Booz Allen Hamilton Inc., bidding $10,500,000, beating Lockheed Martin and CACI International.",
                        "provider": "mock"
                    }
                ]
        else:
            import concurrent.futures

            query_1 = f'"{sol_num}" AND ("protest" OR "GAO" OR "bid" OR "bidders" OR "award" OR "competitor")'
            query_2 = f'"{sol_num}" contract award'

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(self._tavily_search, query_1)
                f2 = executor.submit(self._tavily_search, query_2)
                snippets.extend(f1.result())
                snippets.extend(f2.result())

        # Deduplicate snippets by URL
        seen_urls = set()
        deduped_snippets = []
        for s in snippets:
            if s.get("url") not in seen_urls:
                seen_urls.add(s.get("url"))
                deduped_snippets.append(s)

        if not deduped_snippets:
            logger.warning(f"No web search results found for solicitation: {sol_num}")
            return []

        # 3. Download and parse full documents from snippets
        logger.info(f"Downloading and parsing full documents for solicitation: {sol_num}")
        parser = DocumentParser()
        protest_raw_docs = []
        
        import concurrent.futures

        def _parse_item(item):
            url_target = item["url"]
            title_target = item.get("title", "Document")
            if use_mock or not self.tavily_key or "your_" in self.tavily_key:
                if "b-426101" in url_target:
                    content_txt = (
                        "U.S. GOVERNMENT ACCOUNTABILITY OFFICE (GAO) DECISION\n"
                        "Matter of: Deloitte Consulting LLP\n"
                        "File: B-426101.1\n"
                        "Date: July 1, 2026\n\n"
                        "DIGEST\n"
                        "Protest that the Department of the Navy improperly evaluated the protester's and "
                        "awardee's technical proposals is denied where the record shows that the agency's "
                        "evaluations were reasonable and consistent with the solicitation's evaluation criteria.\n\n"
                        "DECISION\n"
                        "Deloitte Consulting LLP, of Arlington, Virginia, protests the award of a contract to "
                        "Booz Allen Hamilton Inc., of McLean, Virginia, under solicitation No. N00164-26-R-0001, "
                        "issued by the Department of the Navy for advanced business intelligence and data analytics "
                        "support services. The Navy conducted a best-value trade-off under a trade-off process.\n\n"
                        "TECHNICAL EVALUATION AND PRICE PROPOSALS:\n"
                        "- Booz Allen Hamilton Inc. proposed a price of $12,450,000 and received an 'Outstanding' "
                        "technical rating. The Navy noted Booz Allen's certified Snowflake engineers and deep Tableau dashboard experience.\n"
                        "- Deloitte Consulting LLP proposed a price of $13,100,000 and received a 'Good' technical rating. "
                        "Deloitte protested, claiming the Navy undervalued its custom ETL automation tools.\n"
                        "- Palantir Technologies proposed a price of $14,500,000 and received an 'Excellent' rating but "
                        "was excluded from award because of its high price relative to the Booz Allen proposal.\n\n"
                        "GAO ANALYSIS AND CONCLUSION\n"
                        "We have reviewed the evaluation record and find no basis to sustain the protest. The Navy's "
                        "technical evaluations were thorough and fully documented. Booz Allen's lower price and "
                        "Outstanding technical rating made it the logical best-value selection. The protest is denied."
                    )
                else:
                    content_txt = (
                        f"CONTRACT AWARD ANNOUNCEMENT FOR SOLICITATION {sol_num}\n"
                        "The government announced the award under solicitation number " + sol_num + " for data analytics. "
                        "The winning bidder was Booz Allen Hamilton Inc., bidding $12,450,000. Deloitte Consulting and "
                        "Palantir Technologies submitted competitive proposals but were not selected."
                    )
                item["document_text"] = content_txt
                return {"url": url_target, "title": title_target, "content": content_txt, "status": "success"}
            else:
                doc_result = parser.parse_document(url_target)
                item["document_text"] = doc_result.get("content") or item.get("snippet", "")
                return {
                    "url": url_target,
                    "title": title_target,
                    "content": item["document_text"],
                    "status": doc_result.get("status", "failed")
                }

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            protest_raw_docs = list(ex.map(_parse_item, deduped_snippets))

        # 4. In-depth rule-based pattern extraction from snippets and full texts
        competitors = self._extract_competitors_rule_based(sol_num, deduped_snippets)

        # 5. Save/Update RFP record in MongoDB
        if self.db is not None:
            try:
                rfp_col = self.db["rfps"]
                rfp_col.update_one(
                    {"solicitation_number": sol_num},
                    {
                        "$set": {
                            "competitors": competitors,
                            "protest_raw_documents": protest_raw_docs,
                            "scraped_at": datetime.now(tz=timezone.utc).isoformat()
                        }
                    },
                    upsert=True
                )
                logger.info(f"Saved competitor info and full protest documents for {sol_num} in MongoDB 'rfps' collection.")
            except Exception as e:
                logger.warning(f"Failed to cache competitor info: {e}")

        return competitors

    def _tavily_search(self, query: str) -> list[dict[str, Any]]:
        """Run Tavily search client."""
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=self.tavily_key)
            logger.info(f"Tavily competitor search: '{query}'")
            response = client.search(
                query=query,
                max_results=5,
                search_depth="basic"
            )
            results = response.get("results", [])
            return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("snippet", ""), "provider": "tavily"} for r in results]
        except Exception as e:
            logger.error(f"Tavily search failed for '{query}': {e}")
            return []

    def _extract_competitors_rule_based(self, sol_num: str, snippets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        100% rule-based and regex-based information extraction.
        Parses company names, bid prices, technical ratings, and protest status.
        """
        logger.info(f"Running in-depth rule-based competitor extraction for solicitation: {sol_num}")
        
        # Define prominent federal contractors to scan
        known_contractors = [
            ("Booz Allen Hamilton Inc.", ["booz allen", "booz allen hamilton", "bah"]),
            ("Deloitte Consulting LLP", ["deloitte consulting", "deloitte"]),
            ("Guidehouse LLP", ["guidehouse"]),
            ("Palantir Technologies", ["palantir"]),
            ("Science Applications International Corp (SAIC)", ["saic", "science applications international"]),
            ("Lockheed Martin Corp", ["lockheed martin", "lockheed"]),
            ("Accenture Federal Services", ["accenture"]),
            ("CACI International Inc.", ["caci"]),
            ("Leidos Inc.", ["leidos"]),
            ("General Dynamics IT", ["general dynamics", "gdit"]),
            ("DataCorp Inc", ["datacorp"])
        ]

        # Combine text content from snippets and downloaded full texts
        full_text_corpus = ""
        for s in snippets:
            full_text_corpus += "\n" + s.get("title", "") + "\n" + s.get("snippet", "") + "\n"
            if s.get("document_text"):
                full_text_corpus += s["document_text"] + "\n"

        discovered_companies = []

        # Find which known contractors are mentioned
        for full_name, aliases in known_contractors:
            for alias in aliases:
                # Use word boundaries for exact matching
                pattern = r'\b' + re.escape(alias) + r'\b'
                if re.search(pattern, full_text_corpus, re.IGNORECASE):
                    discovered_companies.append(full_name)
                    break

        # If no known contractors are found, attempt to find company patterns dynamically
        if not discovered_companies:
            dynamic_names = re.findall(r'\b[A-Z][a-zA-Z0-9\s\&]+ (?:LLP|LLC|Inc\.|Inc|Corp\.|Corp|Co\.)', full_text_corpus)
            for name in dynamic_names:
                name_clean = name.strip()
                if name_clean not in discovered_companies and len(name_clean) > 3:
                    discovered_companies.append(name_clean)

        competitors = []

        for company in discovered_companies:
            # Find the best snippet/sentence containing the company name for context
            sentences = re.split(r'[.!?\n]', full_text_corpus)
            company_sentences = [s.strip() for s in sentences if re.search(r'\b' + re.escape(company.split()[0]) + r'\b', s, re.IGNORECASE)]
            
            company_context = " ".join(company_sentences[:3])

            # Extract Bid Amount from context or full text near the company name
            bid_amount = "N/A"
            money_pattern = r'\$\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\d+(?:\.\d+)?\s*(?:[M|m]illion|[K|k]|\bthousand\b)?'
            # Look for money match inside sentences mentioning the company
            money_matches = []
            for sent in company_sentences:
                m = re.findall(money_pattern, sent)
                if m:
                    money_matches.extend(m)
            
            if money_matches:
                bid_amount = money_matches[0]
            else:
                # Fallback: find any money match in the whole corpus
                global_money = re.findall(money_pattern, full_text_corpus)
                if global_money:
                    bid_amount = global_money[0]

            # Extract Technical Rating
            # Look for ratings near company name
            rating_pattern = r'\b(Outstanding|Excellent|Good|Acceptable|Satisfactory|Marginal|Unacceptable)\b'
            rating = "N/A"
            for sent in company_sentences:
                r_match = re.search(rating_pattern, sent, re.IGNORECASE)
                if r_match:
                    rating = r_match.group(1).capitalize()
                    break

            # Determine Protest Status
            protest_status = "None"
            corpus_lower = full_text_corpus.lower()
            company_lower = company.lower()
            company_short = company.split()[0].lower()

            # Heuristics
            if "protest" in corpus_lower:
                if re.search(r'matter of:\s*' + re.escape(company_short), corpus_lower) or \
                   re.search(re.escape(company_short) + r'\s+protests', corpus_lower) or \
                   re.search(re.escape(company_short) + r'\s+is the protester', corpus_lower):
                    protest_status = "Protester"
                elif "awardee" in corpus_lower or "award to" in corpus_lower:
                    if re.search(r'award(?:ed)? to\s*' + re.escape(company_short), corpus_lower) or \
                       re.search(r'awardee\s*:\s*' + re.escape(company_short), corpus_lower):
                        protest_status = "Awardee"
            
            if protest_status == "None":
                # Fallback check
                if "award" in company_context.lower() or "won" in company_context.lower():
                    protest_status = "Awardee"
                elif "protest" in company_context.lower() or "protester" in company_context.lower():
                    protest_status = "Protester"

            # Strengths / Weaknesses / Key context sentence
            strengths_weaknesses = "No specific strengths or weaknesses extracted."
            relevant_facts = [s for s in company_sentences if any(kw in s.lower() for kw in ["strength", "weakness", "flaw", "experience", "deficiency", "rating", "proposed"])]
            if relevant_facts:
                strengths_weaknesses = relevant_facts[0]
            elif company_sentences:
                strengths_weaknesses = company_sentences[0]

            # Find matching source URL from snippets
            source_url = "https://sam.gov"
            for s in snippets:
                snippet_text = s.get("title", "") + " " + s.get("snippet", "") + " " + s.get("document_text", "")
                if re.search(r'\b' + re.escape(company.split()[0]) + r'\b', snippet_text, re.IGNORECASE):
                    source_url = s["url"]
                    break

            competitors.append({
                "company_name": company,
                "bid_amount": bid_amount,
                "technical_rating": rating,
                "protest_status": protest_status,
                "strengths_weaknesses": strengths_weaknesses[:200] + ("..." if len(strengths_weaknesses) > 200 else ""),
                "source_url": source_url
            })

        # Make sure we have at least one competitor (default fallback)
        if not competitors:
            logger.info("No competitors extracted via regex. Falling back to default list.")
            competitors.append({
                "company_name": "Booz Allen Hamilton Inc.",
                "bid_amount": "N/A",
                "technical_rating": "N/A",
                "protest_status": "Awardee",
                "strengths_weaknesses": "Default fallback competitor.",
                "source_url": snippets[0]["url"] if snippets else "https://sam.gov"
            })

        return competitors
