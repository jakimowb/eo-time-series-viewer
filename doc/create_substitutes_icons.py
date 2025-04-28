from pathlib import Path

# source dir (location of conf.py)

# Repo for EnMAP-Box documentation
DIR_REPO = Path(__file__).parents[1]
DIR_SOURCE = DIR_REPO / 'doc/source'
DIR_SUBSTITUTIONS = DIR_SOURCE / 'substitutions'

assert DIR_SUBSTITUTIONS.is_dir(), 'Documentation substitutions directory does not exist'
assert DIR_ICONS.is_dir(), 'Documentation source icon directory does not exist'

print('Done')
