"""
bidforge_cli.py
----------------
CLI entry point for the BidForge pipeline (manual RFP upload -> proposal
document), invoked as a subprocess by api/routes/bidforge.py — the same
pattern respond_to_rfp.py uses for the existing prime/subcontract/partnership
pipelines.

Usage:
    python bidforge_cli.py --rfp path/to/rfp.pdf --output my_proposal [--template path/to/template.docx] [--solicitation SOL-123]
"""

import argparse
import sys

from bidforge.pipeline import run_bidforge_pipeline


def main():
    parser = argparse.ArgumentParser(description="Run the BidForge RFP-response pipeline.")
    parser.add_argument("--rfp", required=True, help="Path to the uploaded RFP file (PDF/DOCX/TXT).")
    parser.add_argument("--output", required=True, help="Output filename (without extension).")
    parser.add_argument("--template", default=None, help="Optional path to an uploaded .docx template.")
    parser.add_argument("--solicitation", default="", help="Optional solicitation/reference number.")
    args = parser.parse_args()

    try:
        final_path = run_bidforge_pipeline(
            rfp_file_path=args.rfp,
            output_name=args.output,
            solicitation_number=args.solicitation,
            template_path=args.template,
        )
        print(f"\nSUCCESS: {final_path}")
    except Exception as exc:
        print(f"\nFAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
