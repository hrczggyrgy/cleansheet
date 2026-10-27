#!/usr/bin/env python3
"""
Analytics verification tests - compare CleanSheet results with independent reference computations.
Uses scipy.stats, statsmodels directly (no CleanSheet code).
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.proportion import proportions_ztest
from statsmodels.stats.contingency_tables import Table2x2
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, "/home/lptop/Documents/coding/CleanSheet/src")

DATA_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/data"
RESULTS_DIR = "/home/lptop/Documents/coding/CleanSheet/qa_runs/reference"
os.makedirs(RESULTS_DIR, exist_ok=True)

def hedges_g_independent(x, y):
    """Hedges' g for independent samples."""
    n1, n2 = len(x), len(y)
    var1, var2 = np.var(x, ddof=1), np.var(y, ddof=1)
    pooled_sd = np.sqrt(((n1-1)*var1 + (n2-1)*var2) / (n1 + n2 - 2))
    d = (np.mean(x) - np.mean(y)) / pooled_sd
    # Correction factor
    J = 1 - 3/(4*(n1+n2) - 9)
    return d * J

def hedges_g_paired(diff):
    """Hedges' g for paired samples (using difference scores)."""
    n = len(diff)
    d = np.mean(diff) / np.std(diff, ddof=1)
    J = 1 - 3/(4*n - 9)
    return d * J

def rank_biserial_r(u, n1, n2):
    """Rank-biserial correlation from Mann-Whitney U."""
    return 1 - (2 * u) / (n1 * n2)

def cohens_d_paired(diff):
    """Cohen's d for paired samples."""
    return np.mean(diff) / np.std(diff, ddof=1)

def cramers_v(chi2, n, k):
    """Cramér's V."""
    return np.sqrt(chi2 / (n * (k - 1)))

def epsilon_squared(h, n, k):
    """Epsilon squared for Kruskal-Wallis."""
    return (h - k + 1) / (n - k)

def bootstrap_ci(data, statistic_func, n_bootstrap=2000, confidence=0.95, seed=42):
    """Bootstrap confidence interval."""
    np.random.seed(seed)
    n = len(data)
    boot_stats = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(data, size=n, replace=True)
        boot_stats.append(statistic_func(sample))
    alpha = (1 - confidence) / 2
    return np.percentile(boot_stats, [100*alpha, 100*(1-alpha)])

def compute_welch_reference(group_a, group_b, alternative="two-sided", conf_level=0.95):
    """Reference Welch's t-test using scipy."""
    result = stats.ttest_ind(group_a, group_b, equal_var=False, alternative=alternative)
    
    # Mean difference
    mean_diff = np.mean(group_a) - np.mean(group_b)
    
    # Standard error
    se = np.sqrt(np.var(group_a, ddof=1)/len(group_a) + np.var(group_b, ddof=1)/len(group_b))
    
    # Degrees of freedom (Welch-Satterthwaite)
    df = (np.var(group_a, ddof=1)/len(group_a) + np.var(group_b, ddof=1)/len(group_b))**2 / \
         ((np.var(group_a, ddof=1)/len(group_a))**2/(len(group_a)-1) + (np.var(group_b, ddof=1)/len(group_b))**2/(len(group_b)-1))
    
    # Confidence interval
    t_crit = stats.t.ppf((1 + conf_level) / 2, df)
    ci_low = mean_diff - t_crit * se
    ci_high = mean_diff + t_crit * se
    
    # Effect size: Hedges' g
    g = hedges_g_independent(group_a, group_b)
    
    # Bootstrap CI for Hedges' g
    def g_func(sample):
        # This is a simplified bootstrap - would need paired resampling
        return g
    
    # For bootstrap CI of effect size, we'd need to resample pairs
    # Simplified: use parametric CI for now
    g_se = np.sqrt((len(group_a) + len(group_b)) / (len(group_a) * len(group_b)) + g**2 / (2 * (len(group_a) + len(group_b))))
    g_ci_low = g - 1.96 * g_se
    g_ci_high = g + 1.96 * g_se
    
    return {
        "statistic": float(result.statistic),
        "pvalue": float(result.pvalue),
        "df": float(df),
        "mean_diff": float(mean_diff),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "conf_level": conf_level,
        "hedges_g": float(g),
        "hedges_g_ci_low": float(g_ci_low),
        "hedges_g_ci_high": float(g_ci_high),
        "alternative": alternative
    }

def compute_paired_ttest_reference(pre, post, alternative="two-sided", conf_level=0.95):
    """Reference paired t-test using scipy."""
    diff = post - pre
    result = stats.ttest_rel(post, pre, alternative=alternative)
    
    mean_diff = np.mean(diff)
    se = np.std(diff, ddof=1) / np.sqrt(len(diff))
    df = len(diff) - 1
    
    t_crit = stats.t.ppf((1 + conf_level) / 2, df)
    ci_low = mean_diff - t_crit * se
    ci_high = mean_diff + t_crit * se
    
    # Hedges' g for paired
    g = hedges_g_paired(diff)
    g_se = np.sqrt(1/len(diff) + g**2 / (2*len(diff)))
    g_ci_low = g - 1.96 * g_se
    g_ci_high = g + 1.96 * g_se
    
    return {
        "statistic": float(result.statistic),
        "pvalue": float(result.pvalue),
        "df": float(df),
        "mean_diff": float(mean_diff),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "conf_level": conf_level,
        "hedges_g": float(g),
        "hedges_g_ci_low": float(g_ci_low),
        "hedges_g_ci_high": float(g_ci_high),
        "alternative": alternative
    }

def compute_pearson_reference(x, y, alternative="two-sided", conf_level=0.95):
    """Reference Pearson correlation using scipy."""
    # Remove NaN
    mask = ~(np.isnan(x) | np.isnan(y))
    x_clean = x[mask]
    y_clean = y[mask]
    
    n = len(x_clean)
    if n < 3:
        return {"error": "n < 3"}
    
    r, p = stats.pearsonr(x_clean, y_clean)
    
    # Fisher z transformation
    z = np.arctanh(r)
    se = 1 / np.sqrt(n - 3)
    z_crit = stats.norm.ppf((1 + conf_level) / 2)
    z_low = z - z_crit * se
    z_high = z + z_crit * se
    ci_low = np.tanh(z_low)
    ci_high = np.tanh(z_high)
    
    # For one-sided tests
    if alternative == "less":
        p = p / 2 if r < 0 else 1 - p / 2
    elif alternative == "greater":
        p = p / 2 if r > 0 else 1 - p / 2
    
    return {
        "statistic": float(r),
        "pvalue": float(p),
        "df": float(n - 2),
        "r": float(r),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "conf_level": conf_level,
        "alternative": alternative,
        "n": n
    }

def compute_spearman_reference(x, y, alternative="two-sided", conf_level=0.95):
    """Reference Spearman correlation using scipy."""
    mask = ~(np.isnan(x) | np.isnan(y))
    x_clean = x[mask]
    y_clean = y[mask]
    
    n = len(x_clean)
    if n < 3:
        return {"error": "n < 3"}
    
    rho, p = stats.spearmanr(x_clean, y_clean, alternative=alternative)
    
    # Bootstrap CI for Spearman
    def rho_func(idx):
        return stats.spearmanr(x_clean[idx], y_clean[idx])[0]
    
    indices = np.arange(n)
    boot_rhos = []
    np.random.seed(42)
    for _ in range(2000):
        sample_idx = np.random.choice(indices, size=n, replace=True)
        boot_rhos.append(rho_func(sample_idx))
    
    alpha = (1 - conf_level) / 2
    ci_low = np.percentile(boot_rhos, 100*alpha)
    ci_high = np.percentile(boot_rhos, 100*(1-alpha))
    
    return {
        "statistic": float(rho),
        "pvalue": float(p),
        "rho": float(rho),
        "ci_low": float(ci_low),
        "ci_high": float(ci_high),
        "conf_level": conf_level,
        "alternative": alternative,
        "n": n
    }

def compute_chisquare_reference(table):
    """Reference Chi-square test using scipy."""
    chi2, p, dof, expected = stats.chi2_contingency(table, correction=False)
    
    n = table.sum()
    k = min(table.shape)
    v = np.sqrt(chi2 / (n * (k - 1))) if k > 1 else 0
    
    return {
        "statistic": float(chi2),
        "pvalue": float(p),
        "df": int(dof),
        "cramers_v": float(v),
        "expected": expected.tolist()
    }

def compute_fisher_reference(table, alternative="two-sided"):
    """Reference Fisher's exact test using scipy."""
    # scipy's fisher_exact only works for 2x2
    if table.shape == (2, 2):
        oddsratio, p = stats.fisher_exact(table, alternative=alternative)
        return {
            "statistic": float(oddsratio),
            "pvalue": float(p),
            "odds_ratio": float(oddsratio),
            "alternative": alternative
        }
    else:
        # For larger tables, use statsmodels
        from statsmodels.stats.contingency_tables import Table2x2
        # This is for 2x2 only
        return {"error": "Fisher exact only for 2x2 in scipy"}

def compute_mannwhitney_reference(x, y, alternative="two-sided"):
    """Reference Mann-Whitney U test using scipy."""
    result = stats.mannwhitneyu(x, y, alternative=alternative)
    
    n1, n2 = len(x), len(y)
    u = result.statistic
    r = rank_biserial_r(u, n1, n2)
    
    # Bootstrap CI for rank-biserial
    def r_func(idx_a, idx_b):
        return rank_biserial_r(stats.mannwhitneyu(x[idx_a], y[idx_b]).statistic, len(idx_a), len(idx_b))
    
    indices_a = np.arange(n1)
    indices_b = np.arange(n2)
    boot_rs = []
    np.random.seed(42)
    for _ in range(1000):
        sample_a = np.random.choice(indices_a, size=n1, replace=True)
        sample_b = np.random.choice(indices_b, size=n2, replace=True)
        boot_rs.append(r_func(sample_a, sample_b))
    
    ci_low = np.percentile(boot_rs, 2.5)
    ci_high = np.percentile(boot_rs, 97.5)
    
    return {
        "statistic": float(u),
        "pvalue": float(result.pvalue),
        "rank_biserial_r": float(r),
        "r_ci_low": float(ci_low),
        "r_ci_high": float(ci_high),
        "alternative": alternative,
        "n1": n1,
        "n2": n2
    }

def compute_wilcoxon_reference(pre, post, alternative="two-sided"):
    """Reference Wilcoxon signed-rank test using scipy."""
    diff = post - pre
    # Remove zeros
    diff = diff[diff != 0]
    
    if len(diff) == 0:
        return {"error": "All differences zero"}
    
    result = stats.wilcoxon(diff, alternative=alternative)
    
    # Effect size: rank-biserial for paired
    n = len(diff)
    w = result.statistic
    r = 1 - (2 * w) / (n * (n + 1) / 2) if n > 0 else 0
    
    # Bootstrap CI
    indices = np.arange(n)
    boot_rs = []
    np.random.seed(42)
    for _ in range(1000):
        sample_idx = np.random.choice(indices, size=n, replace=True)
        sample_diff = diff[sample_idx]
        if len(sample_diff) > 0:
            try:
                w_sample = stats.wilcoxon(sample_diff).statistic
                r_sample = 1 - (2 * w_sample) / (len(sample_diff) * (len(sample_diff) + 1) / 2)
                boot_rs.append(r_sample)
            except:
                pass
    
    ci_low = np.percentile(boot_rs, 2.5) if boot_rs else 0
    ci_high = np.percentile(boot_rs, 97.5) if boot_rs else 0
    
    return {
        "statistic": float(w),
        "pvalue": float(result.pvalue),
        "rank_biserial_r": float(r),
        "r_ci_low": float(ci_low),
        "r_ci_high": float(ci_high),
        "alternative": alternative,
        "n": n
    }

def compute_kruskal_reference(groups, alternative="two-sided"):
    """Reference Kruskal-Wallis test using scipy."""
    result = stats.kruskal(*groups)
    
    n = sum(len(g) for g in groups)
    k = len(groups)
    h = result.statistic
    eps2 = epsilon_squared(h, n, k)
    
    return {
        "statistic": float(h),
        "pvalue": float(result.pvalue),
        "df": k - 1,
        "epsilon_squared": float(eps2),
        "n": n,
        "k": k
    }

def compute_dunn_posthoc(groups, group_names):
    """Reference Dunn's post-hoc test with Holm correction."""
    from scipy.stats import rankdata
    from statsmodels.stats.multitest import multipletests
    
    # Combine all data and rank
    all_data = np.concatenate(groups)
    n = len(all_data)
    ranks = rankdata(all_data)
    
    # Split ranks back to groups
    rank_groups = []
    start = 0
    for g in groups:
        rank_groups.append(ranks[start:start+len(g)])
        start += len(g)
    
    # Pairwise comparisons
    comparisons = []
    p_values = []
    for i in range(len(groups)):
        for j in range(i+1, len(groups)):
            ri = np.mean(rank_groups[i])
            rj = np.mean(rank_groups[j])
            ni, nj = len(groups[i]), len(groups[j])
            
            # Standard error
            se = np.sqrt(n * (n + 1) / 12 * (1/ni + 1/nj))
            z = abs(ri - rj) / se
            p = 2 * (1 - stats.norm.cdf(z))
            
            comparisons.append(f"{group_names[i]} vs {group_names[j]}")
            p_values.append(p)
    
    # Holm correction
    rejected, p_adjusted, _, _ = multipletests(p_values, method='holm')
    
    results = []
    for comp, p_raw, p_adj, rej in zip(comparisons, p_values, p_adjusted, rejected):
        results.append({
            "comparison": comp,
            "p_raw": float(p_raw),
            "p_adjusted": float(p_adj),
            "significant": bool(rej)
        })
    
    return results

def run_all_reference_computations():
    """Run reference computations for all test datasets."""
    results = {}
    
    # Load datasets
    datasets = {}
    for fname in os.listdir(DATA_DIR):
        if fname.endswith('.csv'):
            name = fname[:-4]
            path = os.path.join(DATA_DIR, fname)
            try:
                df = pd.read_csv(path)
                datasets[name] = df
            except Exception as e:
                print(f"Could not load {fname}: {e}")
    
    print(f"Loaded {len(datasets)} datasets")
    
    # 1. two_groups - Welch's t-test
    if "two_groups" in datasets:
        df = datasets["two_groups"]
        group_a = df[df["group"] == "A"]["value"].values
        group_b = df[df["group"] == "B"]["value"].values
        
        results["two_groups_welch"] = compute_welch_reference(group_a, group_b)
        results["two_groups_welch_less"] = compute_welch_reference(group_a, group_b, alternative="less")
        results["two_groups_welch_greater"] = compute_welch_reference(group_a, group_b, alternative="greater")
        results["two_groups_welch_90"] = compute_welch_reference(group_a, group_b, conf_level=0.90)
        results["two_groups_welch_99"] = compute_welch_reference(group_a, group_b, conf_level=0.99)
        
        # Mann-Whitney
        results["two_groups_mannwhitney"] = compute_mannwhitney_reference(group_a, group_b)
    
    # 2. paired_wide - Paired t-test (wide format)
    if "paired_wide" in datasets:
        df = datasets["paired_wide"]
        pre = df["pre"].values
        post = df["post"].values
        
        results["paired_wide_ttest"] = compute_paired_ttest_reference(pre, post)
        results["paired_wide_ttest_less"] = compute_paired_ttest_reference(pre, post, alternative="less")
        results["paired_wide_ttest_greater"] = compute_paired_ttest_reference(pre, post, alternative="greater")
        results["paired_wide_ttest_90"] = compute_paired_ttest_reference(pre, post, conf_level=0.90)
        results["paired_wide_ttest_99"] = compute_paired_ttest_reference(pre, post, conf_level=0.99)
        
        # Wilcoxon
        results["paired_wide_wilcoxon"] = compute_wilcoxon_reference(pre, post)
    
    # 3. paired_long - Paired t-test (long format)
    if "paired_long" in datasets:
        df = datasets["paired_long"]
        pre = df[df["occasion"] == "pre"]["value"].values
        post = df[df["occasion"] == "post"]["value"].values
        
        results["paired_long_ttest"] = compute_paired_ttest_reference(pre, post)
        results["paired_long_wilcoxon"] = compute_wilcoxon_reference(pre, post)
    
    # 4. three_groups - Kruskal-Wallis + Dunn post-hoc
    if "three_groups" in datasets:
        df = datasets["three_groups"]
        groups = [df[df["group"] == g]["value"].values for g in ["G1", "G2", "G3"]]
        
        results["three_groups_kruskal"] = compute_kruskal_reference(groups)
        results["three_groups_dunn"] = compute_dunn_posthoc(groups, ["G1", "G2", "G3"])
        
        # Also Welch for pairwise (Games-Howell would be better but using Welch)
        # Pairwise Welch
        for i, g1 in enumerate(["G1", "G2", "G3"]):
            for j, g2 in enumerate(["G1", "G2", "G3"]):
                if i < j:
                    x = df[df["group"] == g1]["value"].values
                    y = df[df["group"] == g2]["value"].values
                    key = f"three_groups_welch_{g1}_vs_{g2}"
                    results[key] = compute_welch_reference(x, y)
    
    # 5. corr - Pearson and Spearman
    if "corr" in datasets:
        df = datasets["corr"]
        # Linear part
        linear = df[df["type"] == "linear"]
        x_lin = linear["x_linear"].values
        y_lin = linear["y_linear"].values
        
        results["corr_pearson_linear"] = compute_pearson_reference(x_lin, y_lin)
        results["corr_pearson_linear_less"] = compute_pearson_reference(x_lin, y_lin, alternative="less")
        results["corr_pearson_linear_greater"] = compute_pearson_reference(x_lin, y_lin, alternative="greater")
        results["corr_pearson_linear_90"] = compute_pearson_reference(x_lin, y_lin, conf_level=0.90)
        results["corr_pearson_linear_99"] = compute_pearson_reference(x_lin, y_lin, conf_level=0.99)
        
        results["corr_spearman_linear"] = compute_spearman_reference(x_lin, y_lin)
        
        # Nonlinear part
        nonlinear = df[df["type"] == "nonlinear"]
        x_nl = nonlinear["x_linear"].values
        y_nl = nonlinear["y_linear"].values
        
        results["corr_pearson_nonlinear"] = compute_pearson_reference(x_nl, y_nl)
        results["corr_spearman_nonlinear"] = compute_spearman_reference(x_nl, y_nl)
    
    # 6. table_2x2 - Chi-square and Fisher
    if "table_2x2" in datasets:
        df = datasets["table_2x2"]
        # Create contingency table
        table = pd.crosstab(df["outcome"], df["group"]).values
        
        results["table_2x2_chisquare"] = compute_chisquare_reference(table)
        results["table_2x2_fisher"] = compute_fisher_reference(table)
        results["table_2x2_fisher_less"] = compute_fisher_reference(table, alternative="less")
        results["table_2x2_fisher_greater"] = compute_fisher_reference(table, alternative="greater")
    
    # 7. table_3x4 - Chi-square
    if "table_3x4" in datasets:
        df = datasets["table_3x4"]
        table = df.pivot_table(index="row", columns="col", values="count", aggfunc="sum", fill_value=0).values
        
        results["table_3x4_chisquare"] = compute_chisquare_reference(table)
    
    # 8. penguins - various tests
    if "penguins" in datasets:
        df = datasets["penguins"]
        # Drop NaN
        df_clean = df.dropna()
        
        # Welch: bill_length_mm by sex (2 groups)
        if "bill_length_mm" in df_clean.columns and "sex" in df_clean.columns:
            sexes = df_clean["sex"].unique()
            if len(sexes) >= 2:
                x = df_clean[df_clean["sex"] == sexes[0]]["bill_length_mm"].values
                y = df_clean[df_clean["sex"] == sexes[1]]["bill_length_mm"].values
                results["penguins_welch_bill_by_sex"] = compute_welch_reference(x, y)
                results["penguins_mannwhitney_bill_by_sex"] = compute_mannwhitney_reference(x, y)
        
        # Pearson: bill_length vs bill_depth
        if "bill_length_mm" in df_clean.columns and "bill_depth_mm" in df_clean.columns:
            x = df_clean["bill_length_mm"].values
            y = df_clean["bill_depth_mm"].values
            results["penguins_pearson_bill"] = compute_pearson_reference(x, y)
            results["penguins_spearman_bill"] = compute_spearman_reference(x, y)
        
        # Chi-square: species vs island
        if "species" in df_clean.columns and "island" in df_clean.columns:
            table = pd.crosstab(df_clean["species"], df_clean["island"]).values
            results["penguins_chisquare_species_island"] = compute_chisquare_reference(table)
        
        # Kruskal: bill_length by species (3 groups)
        if "bill_length_mm" in df_clean.columns and "species" in df_clean.columns:
            species = df_clean["species"].unique()
            groups = [df_clean[df_clean["species"] == s]["bill_length_mm"].values for s in species]
            results["penguins_kruskal_bill_by_species"] = compute_kruskal_reference(groups)
            results["penguins_dunn_bill_by_species"] = compute_dunn_posthoc(groups, list(species))
    
    # 9. edge_cases - test with NaN/inf
    if "edge_cases" in datasets:
        df = datasets["edge_cases"]
        # Test with NaN/inf in numeric column
        numeric = df["numeric"].values
        finite_mask = np.isfinite(numeric)
        clean_numeric = numeric[finite_mask]
        print(f"edge_cases: {len(numeric)} total, {len(clean_numeric)} finite")
    
    # 10. null_tokens - test null token parsing
    if "null_tokens" in datasets:
        df = datasets["null_tokens"]
        print(f"null_tokens: {df['mixed'].tolist()}")
    
    # 11. constant_column - test zero variance
    if "constant_column" in datasets:
        df = datasets["constant_column"]
        const = df["constant"].values
        varying = df["varying"].values
        results["constant_column_pearson"] = compute_pearson_reference(const, varying)
    
    # 12. single_row - test n=1
    if "single_row" in datasets:
        df = datasets["single_row"]
        print(f"single_row: {df.shape}")
    
    # 13. header_only - test empty
    if "header_only" in datasets:
        df = datasets["header_only"]
        print(f"header_only: {df.shape}")
    
    # Save reference results
    with open(os.path.join(RESULTS_DIR, "reference_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nSaved {len(results)} reference computations to {RESULTS_DIR}/reference_results.json")
    return results

if __name__ == "__main__":
    run_all_reference_computations()