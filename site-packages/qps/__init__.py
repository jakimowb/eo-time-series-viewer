import sys
try:
    import qps.qpsresources
    qpsresources.qInitResources()
except Exception as ex:

    print(ex, file=sys.stderr)
    print('It might be required to compile the qps/resources.py first', file=sys.stderr)