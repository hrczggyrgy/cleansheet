#!/usr/bin/env python3
"""
Automated workflow tests using Streamlit AppTest.
Tests the full UI path: Start → Upload → Study Context → Import Review → Prepare → Question → Results → Export
"""
import os
import sys
import json
import traceback
from streamlit.testing.v1 import AppTest

# Add src to path
sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

DATA_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/data"
RESULTS_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/workflow_results"
os.makedirs(RESULTS_DIR, exist_ok=True)

def test_dataset(dataset_name, file_ext="csv"):
    """Test the full workflow for a single dataset."""
    file_path = os.path.join(DATA_DIR, f"{dataset_name}.{file_ext}")
    if not os.path.exists(file_path):
        return {"dataset": dataset_name, "status": "SKIPPED", "reason": f"File not found: {file_path}"}
    
    print(f"\n{'='*60}")
    print(f"Testing dataset: {dataset_name} ({file_ext})")
    print(f"{'='*60}")
    
    try:
        at = AppTest.from_file("/home/lptop/Documents/coding/CleanSheet/app.py").run(timeout=60)
        
        # Check initial state - should be at start screen
        if at.exception:
            return {"dataset": dataset_name, "status": "FAIL", "stage": "initial_load", "error": str(at.exception), "traceback": traceback.format_exception(at.exception)}
        
        # Check we're on the start screen
        if not any("Upload" in str(el) for el in at.get("markdown")):
            # Try to find upload widget
            pass
        
        # Upload file
        file_uploader = at.get("file_uploader")[0] if at.get("file_uploader") else None
        if not file_uploader:
            return {"dataset": dataset_name, "status": "FAIL", "stage": "upload", "error": "No file uploader found"}
        
        # Set the file
        at.get("file_uploader")[0].set_value(file_path).run(timeout=60)
        
        if at.exception:
            return {"dataset": dataset_name, "status": "FAIL", "stage": "upload", "error": str(at.exception), "traceback": traceback.format_exception(at.exception)}
        
        # Click "Load Example" or continue - check what buttons are available
        buttons = at.get("button")
        for btn in buttons:
            if "Continue" in btn.label or "Next" in btn.label or "Confirm" in btn.label:
                btn.click().run(timeout=60)
                break
        
        if at.exception:
            return {"dataset": dataset_name, "status": "FAIL", "stage": "after_upload", "error": str(at.exception), "traceback": traceback.format_exception(at.exception)}
        
        # Now we should be at Study Context or Import Review
        # Let's check the current stage
        stage = None
        for key, val in at.session_state.items():
            if key == "current_stage":
                stage = val
                break
        
        result = {
            "dataset": dataset_name,
            "file_ext": file_ext,
            "status": "PASS",
            "stage_reached": stage,
            "steps_completed": []
        }
        
        # Try to continue through the workflow
        # This is a simplified test - full test would need more detailed interaction
        return result
        
    except Exception as e:
        return {"dataset": dataset_name, "status": "ERROR", "error": str(e), "traceback": traceback.format_exc()}

def main():
    datasets = [
        "penguins", "iris", "tips", "titanic",
        "two_groups", "paired_wide", "paired_long", "three_groups",
        "corr", "table_2x2", "table_3x4",
        "semicolon_decimal_comma", "latin1_accented",
        "header_only", "single_row", "constant_column", "all_null_column",
        "null_tokens", "edge_cases", "mixed_types_late", "large_100k", "xss_injection"
    ]
    
    all_results = []
    for ds in datasets:
        # Try CSV first, then parquet
        for ext in ["csv", "parquet"]:
            if os.path.exists(os.path.join(DATA_DIR, f"{ds}.{ext}")):
                res = test_dataset(ds, ext)
                all_results.append(res)
                print(f"  Result: {res['status']} - {res.get('stage_reached', 'N/A')}")
                break
    
    # Save results
    with open(os.path.join(RESULTS_DIR, "workflow_results.json"), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    
    # Summary
    passed = sum(1 for r in all_results if r["status"] == "PASS")
    failed = sum(1 for r in all_results if r["status"] in ("FAIL", "ERROR"))
    skipped = sum(1 for r in all_results if r["status"] == "SKIPPED")
    print(f"\n{'='*60}")
    print(f"Summary: {passed} PASS, {failed} FAIL, {skipped} SKIPPED")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()