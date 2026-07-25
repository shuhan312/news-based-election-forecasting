"""Phase 4 - Article Text Normalisation pipeline.

One module pair per step (pure rules + IO runner), consuming the
frozen eligibility outputs and producing versioned artefacts:

    Step 1  normalisation_input / build_normalisation_input
            lock the eligible population, select each article's text
            source, freeze the manifest
    Step 2  html_clean / build_html_cleaned_articles
            conservative HTML and web-template cleaning
    Step 3  char_normalise / build_char_normalised_articles
            Unicode/encoding/character normalisation (NFC)

Later steps append here. Data outputs stay flat under
news_collection/ with the _v1 version suffix.
"""
