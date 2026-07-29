"""Streamlit interface for the no-news baseline.

The app reads bundles and contracts; it never extracts from the workbook and
never fits a model in-process. Training is invoked through the CLI so that
every figure the app displays came from a command that can be re-run.
"""
