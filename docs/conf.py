#!/usr/bin/env python3
"""
Configuration file for the Sphinx documentation builder.
"""

import os
import re
import sys
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.abspath('..'))

# Ensure safe environment defaults for docs builds (RTD / local)
os.environ.setdefault('DISABLE_DB', 'true')
os.environ.setdefault('SPHINX_MOCK_IMPORTS', 'true')
os.environ.setdefault('BOT_TOKEN', 'dummy_bot_token_for_docs')
os.environ.setdefault('MONGODB_URL', 'mongodb://localhost:27017/test')

# -- Project information -----------------------------------------------------
project = 'Code Keeper Bot'
copyright = f'{datetime.now().year}, Development Team'
author = 'Development Team'
release = '1.0.0'
version = '1.0'

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.intersphinx',
    'sphinx_autodoc_typehints',
    'sphinx_rtd_theme',
]

# Napoleon settings for Google and NumPy style docstrings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_preprocess_types = True

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__',
    'show-inheritance': True,
}
autodoc_typehints = 'description'
autodoc_mock_imports = [
    # DB drivers and BSON
    'pymongo', 'motor', 'bson',
    # External services and heavy deps
    'fuzzywuzzy', 'python_levenshtein', 'Levenshtein',
    'redis', 'aioredis', 'celery', 'psutil', 'sentry_sdk',
    # Web frameworks and servers (not needed for docs)
    'flask', 'uvicorn', 'gunicorn', 'telegram', 'telegram.ext',
    # Google APIs
    'google', 'googleapiclient', 'googleapiclient.discovery', 'google.oauth2',
    # GitHub API
    'github', 'PyGithub',
    # Missing/optional libs used by modules that break autodoc on RTD
    'cairosvg', 'aiohttp', 'textstat', 'langdetect', 'pytest', 'search_engine', 'code_processor', 'integrations',
]

# Todo extension settings
todo_include_todos = True

# Templates path
templates_path = ['_templates']

# List of patterns to exclude
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', 'api/get-pip.rst']

# The language for content
# שפת תוכן ברירת מחדל. RTD לעיתים מגדיר EN מחוץ ל-conf; לא נכשל אם יש שונות.
language = os.environ.get('SPHINX_LANGUAGE', 'he')

# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    'navigation_depth': 4,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'includehidden': True,
    'titles_only': False,
    'prev_next_buttons_location': 'both',
}
 

# Static files
html_static_path = ['_static']

# Custom sidebar templates
html_sidebars = {
    '**': [
        'globaltoc.html',
        'relations.html',
        'sourcelink.html',
        'searchbox.html',
        'versions.html',
    ]
}

# Suppress noisy autodoc warnings for mocked imports
suppress_warnings = [
    'autodoc',
    'autodoc.import_object',
    'autodoc.mocked',
]

# -- Options for intersphinx extension ---------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'telegram': ('https://docs.python-telegram-bot.org/en/stable/', None),
    'pymongo': ('https://pymongo.readthedocs.io/en/stable/', None),
}

# -- Options for LaTeX output ------------------------------------------------
latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '10pt',
}

# -- Extension configuration -------------------------------------------------
def setup(app):
    app.add_css_file('custom.css')