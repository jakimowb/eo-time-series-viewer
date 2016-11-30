import os, fnmatch
import six

jp = os.path.join
dn = os.path.dirname
mkdir = lambda p: os.makedirs(p, exist_ok=True)

DIR = os.path.dirname(__file__)
DIR_REPO = os.path.dirname(DIR)
DIR_SITE_PACKAGES = jp(DIR_REPO, 'site-packages')
DIR_UI = jp(DIR,*['ui'])

DEBUG = True

def dprint(text, file=None):
    if DEBUG:
        six._print('DEBUG::{}'.format(text), file=file)


def file_search(rootdir, wildcard, recursive=False, ignoreCase=False):
    assert rootdir is not None
    if not os.path.isdir(rootdir):
        six.print_("Path is not a directory:{}".format(rootdir), file=sys.stderr)

    results = []

    for root, dirs, files in os.walk(rootdir):
        for file in files:
            if (ignoreCase and fnmatch.fnmatch(file.lower(), wildcard.lower())) \
                    or fnmatch.fnmatch(file, wildcard):
                results.append(os.path.join(root, file))
        if not recursive:
            break
    return results
