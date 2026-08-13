# Logbook
##2026-06-10 - First Meeting with Mr. Antony Sommerfeld
** Attendees: Shuhan Liu, Mr. Antony Sommerfeld

**Discussed:**
- Talked about the overall direction of the project: using AI to go from just monitoring the news to actually predicting consequences. The idea is to read the news flow, sort it by topic, sector, location, how urgent it is, and possible market impact, then try to predict what might happen as a result.
- Antony suggested I focus on UK politics and voting patterns — basically linking news from the BBC, the Guardian and social media to how each borough voted in the general election.
- We also talked about a backup option: predicting commodity or carbon prices and adding a news context layer on top, building on Simranjit's earlier work.
- For the output, the plan is to build a small prototype that takes news articles as input and produces a structured event report (category, summary, key entities, event type).
- The main thing is that the AI shouldn't just tag things — it needs to actually give some useful judgement, like what the news means, who it affects, and what should happen next.

**Decisions:**
- I'll be doing this as a solo project.
- The project plan deadline got pushed back from this Friday to next Friday which is 19 June (so I have an extra week).
- I'll use the Imperial GitHub repo since Imperial needs access for code review.
- For this year's focus, we're going with voting patterns rather than commodity prices.

**Resources provided:**
- Past Imperial student papers (already sent over email).
- UK general election news article downloads + voting pattern data (still to be sent).
- Project guidance and an example project plan based on voting patterns (still to be sent).

**Pending confirmation:**
- A fixed weekly Zoom time — Antony will confirm.
- Where/when we meet in person, probably the Lansdowne Club in Mayfair, maybe in about two weeks.
- Antony still needs to look over my preliminary research file.

**Action items:**
- Me: send a WhatsApp with my mobile number to join the project group.
- Me: send Antony a draft of the project plan to review before I submit it to Imperial.
- Antony: send over the transcript, project guidance, and an example project plan structure.
- Antony: confirm the weekly Zoom time and the in-person meeting details.
- Antony: look into UK voting pattern datasets we could use.

**Next meetings:**
- Next week: weekly Zoom call, time TBC.
- The week after: in-person meeting in London, probably at the Lansdowne Club.


## 2026-07-03 - In-person Meeting with Mr. Antony Sommerfeld
**Attendees:** Shuhan Liu, Mr. Antony Sommerfeld

**Discussed:**
- The case study will likely be a UK political event, such as local council elections, using historical news and election data from 2021 to 2026. The working structure is 2021-2025 as training data and 2026 as validation data, given the recent local council elections. The exact election type will depend on the volume and quality of available data.
- The central theme is how to extract "context" from news articles. Context matters because the meaning of an event depends on the stakeholder's perspective — e.g. conflict in Iran may be positive for an oil trader holding a long position but negative from a humanitarian or local civilian perspective. Context here may include keywords, article structure, sentiment, prose analysis, word count, topic signals and other extracted features.
- News data will be sourced through a news API and filtered for relevance to specific UK boroughs, councils and political parties. Surrey was discussed as a possible example, including its sub-boroughs and council-level political dynamics. Parties of interest: Reform UK, the Conservatives, Labour, the Green Party and the Liberal Democrats. Reform UK was noted as a particularly interesting case because of its recent growth.
- The project needs a robust approach to categorising articles. Some categorisation may come from the news API directly; otherwise an LLM-based classification process may be required at scale. Categories could include finance, energy, local government and infrastructure, with subcategories such as local council finance, electricity prices or gas prices.
- The AI component has three parts: (1) extracting context from each article, (2) categorising and subcategorising articles, (3) testing different AI models against the 2026 validation data to see which best predicts electoral outcomes — winning party, vote share, turnout and related measures.

**Decisions:**
- Case study direction: UK local council elections, with Surrey (its boroughs, councils and party dynamics) as the working example.
- Train/validation split: news and election data from 2021-2025 for training, 2026 for validation.

**Pending confirmation:**
- The exact election type and geographic scope, depending on the volume and quality of news data we can actually obtain.
- Whether the news API's own categorisation is sufficient or an LLM-based classification pipeline is needed.

**Action items:**
- Me: assess what news data is actually obtainable — test news API feasibility (historical depth, local coverage) and report back with concrete numbers.
- Me: start building the data collection pipeline for Surrey-related news.
- Antony: send over the historical news and election datasets discussed.

**Next meeting:**
- Weekly call, time TBC.


## 2026-07-13 - Weekly Progress Update

**Progress completed:**

- Set up a reproducible project structure for collecting, checking and analysing Surrey local-election and news data.

- Tested both Guardian and NewsAPI collection approaches. Because NewsAPI has limited historical depth and local Surrey coverage, Guardian is currently the main reproducible news source.

- Collected 4,574 Guardian articles using Surrey, council, political-party and context-related queries, then filtered these to 2,210 articles in relevant news sections. Only 125 filtered articles name a specific Surrey council, and only 2 of these were published before May 2026. This means the current news corpus has limited ward- and council-level local detail.

- Built monthly news features for party mentions and themes, and created an initial model dataset linking pre-election news features and previous ward results to 2021-2024 ward outcomes. Because the current news features are mainly shared across wards within the same year, they are a starting point for analysis rather than sufficient ward-level predictors.

- Built a script-generated Surrey election calendar covering 2017-2026. The calendar records the older Surrey council elections used for training and the 2026 East and West Surrey unitary elections proposed for later validation.

- Extracted candidate-level election results from cached source pages. The raw dataset now contains 4,390 candidate records: 4,165 scheduled-election records and 225 by-election records.

**Election-data quality work:**

- Added year-by-year checks for previous ward-result matching. Because the original 2021-2024 collection did not include enough earlier elections to find predecessors for some wards, especially around the 2023 all-out elections, the election history was extended back to 2017. The earlier years are used only as historical information; model rows remain from 2021 onwards.

- Separated scheduled elections from by-elections. Because a by-election can occur later in the same ward and otherwise be merged with the normal election, the raw file now retains both event types while ward-level training outcomes use scheduled elections only.

- Standardised clear party-name variants while retaining the original source labels. This prevents clear aliases such as "Reform" and "Reform UK" from being treated as different parties, while avoiding unsupported assumptions about different local residents' groups.

- Added multi-seat ward information, including seats_contested, candidate rank, elected-candidate status and party seats won where the source supports them. Because one ward can elect more than one councillor and one voter can vote for multiple candidates, the highest-polling candidate's result is now labelled as a best-candidate party proxy rather than a full party vote share.

- Replaced the old ambiguous turnout field with people_who_voted, registered_voters, turnout_percent, turnout_data_source and turnout_is_reliable. This was necessary because source tables may provide a turnout percentage, a voting count, both, or neither; in multi-seat wards, summing candidate votes does not give the number of people who voted.

- Added audit_turnout.py and turnout_audit.csv. The audit checks what each source table actually provides before results are aggregated. If a turnout value is missing, conflicting or unsupported, the relevant field remains empty and is marked unreliable rather than guessed. Therefore, turnout can currently be used only for the reliable subset of wards and should not yet be treated as a universal modelling target.

- Added automated validation checks for election type, party labels, seat allocation, turnout fields and source-table consistency.

- Corrected a duplicated 2022 Reigate and Banstead ward label. Two different source tables were both labelled "Banstead Village", but they had different ward headings, candidates, vote totals and turnout figures. The parser now keeps Banstead Village and Lower Kingswood, Tadworth and Walton as separate ward outcomes, preventing their candidate results, party outcomes and turnout from being merged.

**Current position:**

- The election pipeline now produces reproducible candidate, ward-party and ward-outcome data for 2017-2024, including 838 scheduled-election ward outcomes.

- The initial model dataset contains 2021-2024 ward contests with pre-election news features and historical ward-result features. It is an initial research dataset, not yet a final predictive model.

- All tracked election CSV outputs were regenerated from the scripts after each correction rather than manually edited.

**Current limitations and questions for discussion:**

- Because Guardian provides limited local Surrey coverage before elections, more geographically specific news sources or a better location-extraction method may be needed before ward-level prediction is credible.

- In multi-seat wards, top_polling_party is a clear and consistently available outcome proxy, but it is not identical to full party vote share or complete seat control. The primary outcome should be agreed before model evaluation begins.

- Turnout is not consistently available or comparable across all source tables. It should remain a secondary outcome until reliable coverage is established.

- The 2026 East and West Surrey unitary elections use a new local-government structure. A defensible geographic crosswalk is needed before they can be treated as a direct validation set against the older council data.

**Next actions:**

- Agree the primary election outcome with the supervisor, likely top_polling_party or party-seat outcome where reliable.

- Decide whether 2026 should be used as direct validation after a geographic crosswalk, or as a separate structural-change case study.

- Create a small manually labelled set of news articles for relevance, location, topic and stakeholder context.

- Compare rule-based and LLM-based context classification against that labelled set.

- Build more geographically specific pre-election news features before testing baseline prediction models.


## 2026-08-11 - Stage 1 Results Review Call with Mr. Antony Sommerfeld
**Attendees:** Shuhan Liu, Mr. Antony Sommerfeld

**Discussed:**
- Went through the Stage 1 model results with Antony, focusing on how to separate the party identity effect from the news tone signal.
- The party dummy result (+0.83) is the primary finding: it shows the original baseline was under-specified, and party identity accounts for the majority of the predictive improvement.
- The within-party centre tone result (+0.2291) is a secondary signal. It should not be presented as a separate predictive gain on top of the baseline news result; its value is showing that the news signal is not merely a proxy for party identity.
- Adding news on top of party dummies only moves the result from 0.83 to 0.85, so the incremental gain is modest. However, the news effect was more consistent across time, holding in 5 of 6 windows against 3 of 6 for party dummies.
- Caution on the stance-beats-volume finding: stance and volume are correlated at −0.778, so the two overlap substantially and the claim should not be overstated.
- Reform/baseline error analysis (window 31–19): in 2021 the baseline error of +12.21 dropped to +3.07 after news — a large adjustment, but I flagged that this mainly reflects an unusually large baseline over-prediction rather than consistently strong news evidence. In 2026 the baseline was already a slight under-prediction (−1.33) and news moved it further to −3.16, so the same directional adjustment produces different outcomes depending on where the baseline sits. Clamping also differs sharply between the two elections: 41.2% of reform prediction instances clamped to zero in 2021 vs 5.7% in 2026 (version 1). Antony found these figures hard to interpret without full election context and asked for the details by email.
- Viva expectations: the panel will be around three people — Antony, the Imperial supervisor, and likely an independent examiner. Examiners this year are focusing hard on whether candidates know their code line by line; presenting results without showing where they come from in the code will not be enough. Antony suggested building a small web app for the viva that takes inputs (party, confidence, data parameters), runs the model live, and displays the relevant code snippets alongside each output so any result can be traced back to a specific function. The viva is arguably the most important element, since it is how examiners verify I actually did the work.
- Feedback logistics: Antony will return a one-to-two page document with section-by-section improvement notes, not line edits or rewrites.

**Decisions:**
- Headline framing: party identity explains most of the predictive improvement, but there is a smaller and potentially more stable within-party news tone signal that is not explained by fixed party identity or volume of coverage.
- The +0.83 party dummy result is the primary finding; the +0.2291 centre tone result is presented as evidence that the news signal is not a proxy for party identity, not as an additional predictive gain.
- Final model check recommended: put party identity, news volume and within-party centre tone into the same specification and test whether centre tone still adds out-of-sample value after controlling for both.
- I will send the finalised write-up to Antony by 9am on Monday 24 August; he will review it during his travel week and return notes by around the 26th, leaving a few days for amendments before submission.
- Viva preparation (the web app demo) starts next week, only after the write-up is finalised and the codebase and results are verified as consistent.

**Pending confirmation:**
- Whether the Imperial supervisor or Marianne Begg will be the second examiner — Antony to confirm.
- Final interpretation of the reform/baseline error figures — Antony will respond after receiving the details by email.
- Whether centre tone survives the combined party + volume + tone specification.

**Action items:**
- Me: send Email 1 — results and analysis, including the reform/baseline error details discussed on the call (today).
- Me: send Email 2 — the full codebase via a file-sharing service so Antony can attempt to replicate the results (today).
- Me: finalise the IRP write-up and send it to Antony by 9am Monday 24 August.
- Me: after the write-up is sent, start building the viva web app linking model outputs to code (next week).
- Antony: send the meeting transcript (today).
- Antony: review the codebase and respond with findings, likely tomorrow afternoon.
- Antony: review the write-up during his travel week and return section-by-section notes by around the 26th.
- Antony: confirm the second examiner.

**Next meeting:**
- No date fixed; next contact by email (Antony responding to the two emails), with further discussion after his review during the week of the 24th.

