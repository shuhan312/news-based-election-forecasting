# Woking South blind test - frozen protocol v1

Election: surrey-county-council-by-election-woking-south-2025-07-10, polling day 2025-07-10.
Evidence tier: news-blind and analyst-blind; baseline-informed (the outcome sat inside Stage 1's rolling-origin training); single contest - a case study, whatever the result.

## The derived window-to-arm assignment

| window | combined | local | national | -> serves the window |
| --- | ---: | ---: | ---: | --- |
| 180_to_91_days | -0.5751 | +0.3247 | -0.5896 | **local** |
| 90_to_31_days | +0.2404 | +0.2671 | +0.2682 | **national** |
| 30_to_15_days | +0.1339 | -0.6587 | -0.0156 | **combined** |
| 14_to_8_days | -0.3252 | +0.0149 | +0.0048 | **local** |
| 7_to_4_days | -0.0097 | -0.0097 | +0.0000 | **national** |
| final_72_hours | +0.1882 | +0.2590 | -0.0231 | **local** |

Derivation rule: largest committed 2026 delta per window; ties at 4 dp fall to alphabetical order. Sources and every other pinned choice: protocol.json (input hashes included).

Stop-loss: abort and record if usable articles < 15. Unseal: only by the named script, only after a predictions file is committed.
