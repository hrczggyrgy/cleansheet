#!/usr/bin/env python3
"""
Run CleanSheet's analytics on test datasets and save results for comparison.
Uses CleanSheet's services directly (headless).
"""
import os
import sys
import json
import numpy as np
import pandas as pd
import polars as pl

sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

from CleanSheet.services.ingest import ingest_file, validate_upload
from CleanSheet.services.profile import run_profiling
from CleanSheet.services.prepare import get_prepared_data
from CleanSheet.services.statistics import run_analysis, AnalysisRequest
from CleanSheet.contracts import (
    DatasetRef, ColumnRole, SemanticRole, StudyDesign, 
    Goal, Method, TransformOp, CleaningStep, ImportSpec, Alternative
)
from CleanSheet.jobs.workspace import WorkspaceManager

DATA_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/data"
RESULTS_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/cleansheet_results"
os.makedirs(RESULTS_DIR, exist_ok=True)

def run_cleansheet_analysis(dataset_name, file_ext="csv"):
    """Run a specific analysis through CleanSheet services."""
    file_path = os.path.join(DATA_DIR, f"{dataset_name}.{file_ext}")
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    
    try:
        # Read file as bytes
        with open(file_path, "rb") as f:
            file_data = f.read()
        
        # Create workspace
        ws_mgr = WorkspaceManager()
        ws = ws_mgr.create()
        
        # Ingest file
        dataset_ref, preview, metadata = ingest_file(ws, file_data, filename=f"{dataset_name}.{file_ext}")
        
        # Profile
        profiling_result = run_profiling(ws, dataset_ref)
        
        # Get column roles from profiling
        column_roles = []
        for col_profile in profiling_result.columns:
            column_roles.append(ColumnRole(
                column=col_profile.name,
                physical_dtype=col_profile.physical_dtype,
                semantic_role=col_profile.semantic_role
            ))
        
        # Build empty recipe (no preparation)
        recipe = []
        
        # Get prepared data
        prepared_df = get_prepared_data(ws, dataset_ref, recipe)
        
        # Run specific analyses based on dataset
        results = {}
        
        if dataset_name == "two_groups":
            # Welch's t-test
            request = AnalysisRequest(
                goal=Goal.COMPARE_TWO_MEANS,
                variables={
                    "outcome": "value",
                    "group": "group"
                },
                group_levels=["A", "B"],
                study_design=StudyDesign.INDEPENDENT,
                estimand="Mean difference (A - B) in value",
                confidence_level=0.95,
                alternative=Alternative.TWO_SIDED
            )
            result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
            results["welch_t"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
            
            # Also test Mann-Whitney
            request_mw = AnalysisRequest(
                goal=Goal.COMPARE_TWO_MEANS,
                variables={
                    "outcome": "value",
                    "group": "group"
                },
                group_levels=["A", "B"],
                study_design=StudyDesign.INDEPENDENT,
                estimand="Mean difference (A - B) in value",
                confidence_level=0.95,
                alternative=Alternative.TWO_SIDED,
                method=Method.MANN_WHITNEY_U
            )
            result_mw = run_analysis(ws, dataset_ref, request_mw, recipe, column_roles)
            results["mann_whitney"] = result_mw.model_dump() if hasattr(result_mw, 'model_dump') else str(result_mw)
        
        elif dataset_name == "paired_wide":
            # Paired t-test wide format
            request = AnalysisRequest(
                goal=Goal.COMPARE_PAIRED_MEANS,
                variables={
                    "pair_id": "subject_id",
                    "pre_col": "pre",
                    "post_col": "post"
                },
                study_design=StudyDesign.PAIRED,
                estimand="Mean difference (post - pre)",
                confidence_level=0.95,
                alternative=Alternative.TWO_SIDED
            )
            result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
            results["paired_ttest_wide"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
        
        elif dataset_name == "paired_long":
            # Paired t-test long format
            request = AnalysisRequest(
                goal=Goal.COMPARE_PAIRED_MEANS,
                variables={
                    "pair_id": "subject_id",
                    "occasion": "occasion",
                    "outcome": "value"
                },
                group_levels=["pre", "post"],
                study_design=StudyDesign.PAIRED,
                estimand="Mean difference (post - pre)",
                confidence_level=0.95,
                alternative=Alternative.TWO_SIDED
            )
            result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
            results["paired_ttest_long"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
        
        elif dataset_name == "three_groups":
            # Kruskal-Wallis
            request = AnalysisRequest(
                goal=Goal.COMPARE_K_MEANS,
                variables={
                    "outcome": "value",
                    "group": "group"
                },
                group_levels=["G1", "G2", "G3"],
                study_design=StudyDesign.INDEPENDENT,
                estimand="Group differences in value across G1, G2, G3",
                confidence_level=0.95,
                method=Method.KRUSKAL_WALLIS
            )
            result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
            results["kruskal"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
        
        elif dataset_name == "corr":
            # Pearson correlation
            request = AnalysisRequest(
                goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
                variables={
                    "outcome": "x_linear",
                    "predictor": "y_linear"
                },
                study_design=StudyDesign.INDEPENDENT,
                estimand="Pearson correlation between x_linear and y_linear",
                confidence_level=0.95,
                alternative=Alternative.TWO_SIDED
            )
            result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
            results["pearson"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
            
            # Spearman
            request_s = AnalysisRequest(
                goal=Goal.EXPLORE_ORDERED_RELATIONSHIP,
                variables={
                    "outcome": "x_linear",
                    "predictor": "y_linear"
                },
                study_design=StudyDesign.INDEPENDENT,
                estimand="Spearman correlation between x_linear and y_linear",
                confidence_level=0.95,
                alternative=Alternative.TWO_SIDED,
                method=Method.SPEARMAN_RHO
            )
            result_s = run_analysis(ws, dataset_ref, request_s, recipe, column_roles)
            results["spearman"] = result_s.model_dump() if hasattr(result_s, 'model_dump') else str(result_s)
        
        elif dataset_name == "table_2x2":
            # Chi-square and Fisher
            request = AnalysisRequest(
                goal=Goal.CATEGORICAL_ASSOCIATION,
                variables={
                    "outcome": "outcome",
                    "group": "group"
                },
                study_design=StudyDesign.INDEPENDENT,
                estimand="Association between outcome and group",
                confidence_level=0.95
            )
            result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
            results["chisquare_fisher"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
        
        elif dataset_name == "penguins":
            df = pd.read_csv(file_path).dropna()
            # Welch: bill_length by sex
            if "bill_length_mm" in df.columns and "sex" in df.columns:
                sexes = sorted(df["sex"].dropna().unique().tolist())[:2]
                request = AnalysisRequest(
                    goal=Goal.COMPARE_TWO_MEANS,
                    variables={
                        "outcome": "bill_length_mm",
                        "group": "sex"
                    },
                    group_levels=sexes,
                    study_design=StudyDesign.INDEPENDENT,
                    estimand=f"Mean difference ({sexes[0]} - {sexes[1]}) in bill_length_mm",
                    confidence_level=0.95,
                    alternative=Alternative.TWO_SIDED
                )
                result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
                results["penguins_welch_bill_by_sex"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
            
            # Pearson: bill_length vs bill_depth
            if "bill_length_mm" in df.columns and "bill_depth_mm" in df.columns:
                request = AnalysisRequest(
                    goal=Goal.EXPLORE_LINEAR_RELATIONSHIP,
                    variables={
                        "outcome": "bill_length_mm",
                        "predictor": "bill_depth_mm"
                    },
                    study_design=StudyDesign.INDEPENDENT,
                    estimand="Pearson correlation between bill_length_mm and bill_depth_mm",
                    confidence_level=0.95,
                    alternative=Alternative.TWO_SIDED
                )
                result = run_analysis(ws, dataset_ref, request, recipe, column_roles)
                results["penguins_pearson_bill"] = result.model_dump() if hasattr(result, 'model_dump') else str(result)
        
        return results
        
    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}

def main():
    datasets_to_test = [
        "two_groups", "paired_wide", "paired_long", "three_groups",
        "corr", "table_2x2", "penguins"
    ]
    
    all_results = {}
    for ds in datasets_to_test:
        print(f"\nTesting {ds}...")
        for ext in ["csv", "parquet"]:
            if os.path.exists(os.path.join(DATA_DIR, f"{ds}.{ext}")):
                res = run_cleansheet_analysis(ds, ext)
                all_results[f"{ds}_{ext}"] = res
                print(f"  Result keys: {list(res.keys()) if isinstance(res, dict) else 'error'}")
                break
    
    with open(os.path.join(RESULTS_DIR, "cleansheet_results.json"), "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\nSaved CleanSheet results to {RESULTS_DIR}/cleansheet_results.json")

if __name__ == "__main__":
    main()