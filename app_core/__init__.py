"""
Core package for parsing HTML pricings and normalizing them for the Streamlit app.

Modules:
- html_utils: HTML helpers (table extraction, row normalization)
- extractors: Issuer-specific table extraction (wraps existing Extractors.py if present)
- normalizers: Issuer-specific normalization + universal cleanup
- cleanup: Universal cleanup applied to all normalized frames
- email_integration: Optional Outlook helpers (safe to import without Outlook)
"""

