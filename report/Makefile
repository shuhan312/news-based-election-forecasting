REPORT_TABLES = a1_stage1_predictors.tex a2a_confirmatory_v1.tex \
	a2b_confirmatory_v2.tex a3_sensitivity_summary.tex \
	a4_seat_accuracy_v2.tex a5_llm_validation.tex \
	a8_approach_comparison.tex a10_blind_tests.tex \
	a11_division_sample.tex a12_cumulative_results.tex \
	a13_content_features.tex a14_eligibility_rules.tex \
	a15_local_sensitivity.tex a17_lopo_results.tex \
	a18_reform_attribution.tex a20_stage2_fitting_cells.tex

.PHONY: force sync-tables clean

report.pdf: report.tex report-template.cls references.bib $(REPORT_TABLES) figures/*
	make force

sync-tables:
	@for table in $(REPORT_TABLES); do \
		cp ../outputs/report_tables_v1/latex/$$table $$table; \
	done

force:
	latexmk -pdf report.tex

clean:
	rm -f *.pdf
	rm -f *.aux
	rm -f *.bbl
	rm -f *.log
	rm -f *.blg
	rm -f *.bcf
	rm -f *.xml
	rm -f *~
	rm -f *.bak
	rm -f *.out
	rm -f *.fdb_latexmk
	rm -f *.fls
	rm -f *.synctex.gz
