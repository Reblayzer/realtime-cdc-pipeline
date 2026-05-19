"""Make the spark/jobs module importable from tests without a full Spark install."""
import os
import sys

# Add the jobs directory to PYTHONPATH so `import transforms` works.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "spark", "jobs"))
