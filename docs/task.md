# Checklist - Separate CR and Cross Section Inspection

- [x] Update `backend/services/product_request_service.py` to fix loose string matching so "CROSS SECTION INSPECTION" count is not overwritten by C-R.
- [x] Update `backend/services/report_generator.py` to return `"CROSS SECTION INSPECTION"` for `{sem_records.` placeholders in `_identify_slide_category()`.
- [x] Verify image path resolution using the test script.
- [x] Create and run a verification script simulating selection of only "CROSS SECTION INSPECTION" and verifying that Slide 11 is kept while Slide 10 is deleted.
- [x] Run a complete end-to-end report generation test.
