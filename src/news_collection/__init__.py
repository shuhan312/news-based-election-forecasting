"""Production Raw News Collection package.

Implements the validated Source Adapter Framework
(news_protocol/source_adapter_framework.md) for the Raw News Collection
stage.  Strictly raw acquisition + provenance: no eligibility rules,
no deduplication, no date resolution, no classification.

Version constants are stamped into every record and log row so any
record can be traced back to the exact software and protocol version
that produced it.
"""

SOFTWARE_VERSION = "news_collection-1.0.0"
PROTOCOL_VERSION = "1.0"          # news_research_protocol.md version
SCHEMA_VERSION = "1.0"            # raw_news_schema.json version
