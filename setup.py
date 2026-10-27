"""
Setup script for CleanSheet package.
This provides a fallback for environments that don't support pyproject.toml fully.
"""
from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open("requirements.txt", "r") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#") and not line.startswith("-e")]

setup(
    name="CleanSheet",
    version="0.1.0",
    description="No-code statistical analysis with Streamlit, Polars 2.0, and seaborn",
    author="CleanSheet Team",
    python_requires=">=3.12",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "streamlit==1.66.0",
        "polars[rtcompat]==2.0.0",
        "pyarrow>=19.0.0",
        "seaborn[stats]==0.13.2",
        "scipy>=1.13.0",
        "statsmodels>=0.14.2",
        "matplotlib>=3.9.0",
        "pydantic>=2.8.0",
        "pydantic-settings>=2.4.0",
        "numpy>=1.26.0",
        "pandas>=2.2.0",
    ],
    entry_points={
        "console_scripts": [
            "cleansheet=CleanSheet.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
