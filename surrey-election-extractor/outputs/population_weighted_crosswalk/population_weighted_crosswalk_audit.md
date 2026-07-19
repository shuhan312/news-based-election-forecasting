# 2021-to-2026 population-weighted crosswalk audit

## Release decision

Population-weighted estimates are reproducible **sensitivity-analysis values only**. They do not replace official NULLs and are not authorised as primary no-news predictors for changed-boundary wards.

## Coverage and validation

- Historical divisions: 81
- 2026 wards: 81
- Assigned 2021 Output Areas: 3662
- Assigned usual-resident population: 1,203,079
- Approved direct wards: 24
- Changed-boundary wards: 57
- Direct-mapping comparable party rows: 90
- Direct-mapping MAE: 0.000000 percentage points
- Maximum direct-mapping error: 0.000000 percentage points

The zero validation error checks implementation and source alignment because the validation wards are unchanged. It cannot establish how votes were distributed inside historical divisions that were split by the 2026 boundaries.

## Official sources

- historical_boundaries: https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/County_Electoral_Divisions_May_2023_Boundaries_EN_BFC/FeatureServer/0
- current_boundaries: https://www10.surreycc.gov.uk/electionmap/
- oa_population_weighted_centroids: https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/OA_December_2021_EW_PWC_V4/FeatureServer/0
- oa_population: https://www.nomisweb.co.uk/census/2021/bulk
- lgbce_surrey_review: https://www.lgbce.org.uk/all-reviews/surrey

## Input fingerprints

- `old_divisions.geojson`: `0a29e00a9de056337ee2602b7b167c6cb403cc6ce390cacdd310afc0ed21171d`
- `east_wards.geojson`: `fbfb3559228e0ad145d73ec7673d594cda1d187790d6391ee69b7d6bac24b091`
- `west_wards.geojson`: `510bc8dde50ece0a3308f15a198d3bbb877b0500d80279471f62318297d7751e`
- `census2021-ts001-oa.csv`: `b56b3571a4943e7e811c0263b2a5377b5a61a1ef1a48be6c5b399dba8825ef02`
- `oa_page_0.geojson`: `110d59b1613d4e1076d515c39f72b8d3c5bce282c5d75c36a190acf91e143b4d`
- `oa_page_2000.geojson`: `2389119d5c8e93ba4d3c1fa2cf616adccf0003df287a99f10b159b530374640d`
- `oa_page_4000.geojson`: `841defea24df55cd739d9f072914db8ff64445970670a92b160729314b2baec7`
- `oa_page_6000.geojson`: `4ae39417a1f62c2f37e7faf61bc066b5f1a11396c3ae524c148572c6c02dab78`
- `oa_page_8000.geojson`: `3e1b51e7cd83d2af0c1b7f6252fa2744266be1b99a0a59aa3174beb43e0cac7d`
- `oa_page_10000.geojson`: `b44d993d51f9060ed3d3dd6595222ea7577d9cbe2b21d28b7ad1e04e460ad1cd`
- `oa_page_12000.geojson`: `6e603f1778059575f036554253e514f4a3b8599721b5cb194b622eb110ec6d77`
- `oa_page_14000.geojson`: `771096f6e0f8b43a6b699ee0446202e80250efbf8b2ae6555259ce0f71d00679`
- `oa_page_16000.geojson`: `63178c5d96b5af090e7474b7810a1277396a6ba4dfff970cae74edf3df447ecb`
- `oa_page_18000.geojson`: `6c1b8888646399ef52121810c6d7fa7c6a9fadbc4d538d176f799b5c931351c0`
- `master_election_database_payload.json`: `9b8fc4318da7720de63ec14f9fe32d5212155ee0dfd592d275a8bb581f8b53e8`
- `historical_reference_permissions.json`: `f695df51f3b3b217071ad0e4ecf52a3364be795177e65a157c52a111c47b6954`

## Ward decisions

| Election | Ward | Mapping | Primary history | Population estimate role |
|---|---|---|---|---|
| surrey-county-council-2026-east-surrey | Caterham Valley | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Warlingham | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Oxted | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | West Ewell | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Ewell Court, Auriol & Cuddington | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Ewell Village, Stoneleigh & Nonsuch | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Caterham Hill | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Godstone | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Lingfield | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Nork & Tattenhams | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Banstead, Woodmansterne & Chipstead | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Redhill West & Meadvale | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Redhill East & North Earlswood | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Dorking Rural | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Dorking | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Dorking Hills | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Ashtead | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Epsom West | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Epsom Town & Downs | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-east-surrey | Tadworth, Walton & Kingswood | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Merstham & Banstead South | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Reigate | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Earlswood & Reigate South | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Horley West, Salfords & Sidlow | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Horley East | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Leatherhead & Fetcham East | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Bookham & Fetcham West | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Cobham & Oxshott South | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Esher, Claygate & Oxshott North | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Long Ditton, Hinchley Wood & Weston Green | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Weybridge | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | West Molesey | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Hersham | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Thames Ditton & East Molesey | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Walton | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-east-surrey | Walton South & Oatlands | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Haslemere | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Goldsworth East & Horsell Village | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Knaphill & Goldsworth West | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Camberley East | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Camberley West & Frimley | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Stanwell, Stanwell Moor & Ashford North | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Ashford | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Sunbury Common & Ashford Common | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Woking North | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Bagshot, Windlesham & Chobham | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Staines | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Staines South & Ashford West | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Englefield Green & Virginia Water | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Egham | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Thorpe, Longcross & Ottershaw | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Chertsey | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Guildford West | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Worplesdon | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Ash | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Shalford | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Guildford East | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Guildford South East | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Guildford North | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Guildford South West | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Lightwater, West End & Bisley | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Heatherside & Parkside | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Frimley Green & Mytchett | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Woking South West | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Woking South East | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Woking South | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Godalming South, Milford & Witley | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Godalming North | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Waverley Eastern Villages | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Waverley Western Villages | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Farnham Central | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Farnham South | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Farnham North | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Shere | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Cranleigh & Ewhurst | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | The Byfleets | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Lower Sunbury & Halliford | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Laleham & Shepperton | approved_direct | direct_history_retained | validation_only |
| surrey-county-council-2026-west-surrey | Woodham & New Haw | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Addlestone | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
| surrey-county-council-2026-west-surrey | Horsleys | changed_boundary | unavailable_after_official_weight_review | sensitivity_analysis_only |
