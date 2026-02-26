from setuptools import setup, find_packages

setup(
    name="h-neurons",
    version="0.1.0",
    description="Find and disable hallucination neurons in LLMs",
    author="Jon Hammant",
    url="https://github.com/jhammant/h-neurons",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.0",
        "transformers>=4.36",
        "datasets>=2.14",
        "scikit-learn>=1.3",
        "numpy>=1.24",
        "accelerate>=0.25",
    ],
    entry_points={
        "console_scripts": [
            "h-neurons=scripts.run_full:main",
        ],
    },
)
