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



