import pathlib

DIR_REPO = pathlib.Path(__file__).parents[1]
DIR_SOURCE = DIR_REPO / 'source'
assert DIR_SOURCE.is_dir()
