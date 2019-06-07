# -*- coding: utf-8 -*-
#
# EO TimeSeriesViewer documentation build configuration file, created by
# sphinx-quickstart on Fri Jan 19 11:57:19 2018.
#
# This file is execfile()d with the current directory set to its
# containing dir.
#
# Note that not all possible configuration values are present in this
# autogenerated file.
#
# All configuration values have a default; values that are commented out
# serve to show the default.

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
import os
import sys
import mock


if True:
    MOCK_MODULES = ['qgis', 'qgis.core', 'qgis.gui', 'qgis.utils', 'numpy', 'scipy',
                'vrtbuilder', 'vrtbuilder.virtualrasters',
                'qgis.PyQt', 'qgis.PyQt.Qt', 'qgis.PyQt.QtCore', 'qgis.PyQt.QtGui', 'qgis.PyQt.QtWidgets', 'qgis.PyQt.QtXml',
                'processing', 'processing.core', 'processing.core.ProcessingConfig']

    for mod_name in MOCK_MODULES:
        sys.modules[mod_name] = mock.Mock()

sys.path.insert(0, os.path.abspath('.'))
sys.path.insert(0, os.path.abspath('../'))
sys.path.insert(0, os.path.abspath('../../'))

#from eotimeseriesviewer.tests import initQgisApplication
#app = initQgisApplication()

try:
    # enable readthedocs to load git-lfs files
    # see https://github.com/rtfd/readthedocs.org/issues/1846
    #     https://github.com/InfinniPlatform/InfinniPlatform.readthedocs.org.en/blob/master/docs/source/conf.py#L18-L31
    # If runs on ReadTheDocs environment
    on_rtd = os.environ.get('READTHEDOCS', None) == 'True'

    if True or on_rtd:
        print('Fetching files with git_lfs')
        DOC_SOURCES_DIR = os.path.dirname(os.path.abspath(__file__))
        PROJECT_ROOT_DIR = os.path.dirname(os.path.dirname(DOC_SOURCES_DIR))
        sys.path.insert(0, DOC_SOURCES_DIR)
        print('PROJECT_ROOT_DIR', PROJECT_ROOT_DIR)

        from git_lfs import fetch
        fetch(PROJECT_ROOT_DIR)
except Exception as ex:
    print(ex)

# -- General configuration ------------------------------------------------

# If your documentation needs a minimal Sphinx version, state it here.
#
# needs_sphinx = '1.0'

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ['sphinx.ext.autodoc',
    'sphinx.ext.doctest',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
    'sphinx.ext.coverage',
    'sphinx.ext.mathjax',
    'sphinx.ext.ifconfig',
    'sphinx.ext.viewcode',
    'sphinx.ext.autosectionlabel'
    ]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
# The suffix(es) of source filenames.
# You can specify multiple suffix as a list of string:
#
source_parsers = {
   '.md': 'recommonmark.parser.CommonMarkParser',
}

source_suffix = ['.rst', '.md']


master_doc = 'index'

# General information about the project.
project = 'EO Time Series Viewer'
copyright = '2018, Benjamin Jakimow, Sebastian van der Linden, Fabian Thiel, Patrick Hostert'
author = 'Benjamin Jakimow, Fabian Thiel'

# The version info for the project you're documenting, acts as replacement for
# |version| and |release|, also used in various other places throughout the
# built documents.
#
# The short X.Y version.
import eotimeseriesviewer
version = u'{}'.format(eotimeseriesviewer.__version__)
# The full version, including alpha/beta/rc tags.
release = u'{}'.format(eotimeseriesviewer.__version__)

# The language for content autogenerated by Sphinx. Refer to documentation
# for a list of supported languages.
#
# This is also used if you do content translation via gettext catalogs.
# Usually you set "language" from the command line for these cases.
language = None

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This patterns also effect to html_static_path and html_extra_path
exclude_patterns = []

# The name of the Pygments (syntax highlighting) style to use.
pygments_style = 'sphinx'

# If true, `todo` and `todoList` produce output, else they produce nothing.
todo_include_todos = True


# -- Options for HTML output ----------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
#html_theme = 'alabaster'
html_theme = 'sphinx_rtd_theme'
# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
html_theme_options = {
    'canonical_url': '',
    'analytics_id': '',
    'logo_only': False,
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': False,
    'vcs_pageview_mode': 'view',
    # Toc options
    'collapse_navigation': True,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False
}
html_logo = 'img/logo.png'
html_favicon = 'img/logo.png'

# Theme options are theme-specific and customize the look and feel of a theme
# further.  For a list of options available for each theme, see the
# documentation.
#
# html_theme_options = {}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

html_css_files = ['custom.css']

# Custom sidebar templates, must be a dictionary that maps document names
# to template names.
#
# This is required for the alabaster theme
# refs: http://alabaster.readthedocs.io/en/latest/installation.html#sidebars
html_sidebars = {
    '**': [
        'about.html',
        'navigation.html',
        'relations.html',  # needs 'show_related': True theme option to display
        'searchbox.html',
        'donate.html',
    ]
}


# -- Options for HTMLHelp output ------------------------------------------

# Output file base name for HTML help builder.
htmlhelp_basename = 'EOTimeSeriesViewerDoc'


# -- Options for LaTeX output ---------------------------------------------

latex_elements = {
    # The paper size ('letterpaper' or 'a4paper').
    #
    # 'papersize': 'letterpaper',

    # The font size ('10pt', '11pt' or '12pt').
    #
    # 'pointsize': '10pt',

    # Additional stuff for the LaTeX preamble.
    #
    # 'preamble': '',

    # Latex figure (float) alignment
    #
    # 'figure_align': 'htbp',
}

# Grouping the document tree into LaTeX files. List of tuples
# (source start file, target name, title,
#  author, documentclass [howto, manual, or own class]).
latex_documents = [
    (master_doc, 'EOTimeSeriesViewer.tex', 'EO Time Series Viewer Documentation',
     'Benjamin Jakimow', 'manual'),
]


# -- Options for manual page output ---------------------------------------

# One entry per manual page. List of tuples
# (source start file, name, description, authors, manual section).
man_pages = [
    (master_doc, 'eotimeseriesviewer', u'EO Time Series Viewer Documentation',
     [author], 1)
]


# -- Options for Texinfo output -------------------------------------------

# Grouping the document tree into Texinfo files. List of tuples
# (source start file, target name, title, author,
#  dir menu entry, description, category)
texinfo_documents = [
    (master_doc, 'EOTimeSeriesViewer', u'EO Time Series Viewer Documentation',
     author, 'EOTimeSeriesViewer', 'One line description of project.',
     'Miscellaneous'),
]




# Example configuration for intersphinx: refer to the Python standard library.
intersphinx_mapping = {'https://docs.python.org/': None,
                       'python':('https://docs.python.org/3.6', None),
                       'http://www.pyqtgraph.org/documentation':None}
