This directory contain external python packages which might be required by QPS.
Each package should be in a folder with prefix 'ext-', to allow them becoming a site-package folder

externals/
  ext-packageX/
     packageX

if packageX is not available, it can be made available to python with:
> import site
> site.addsitedir('externals/ext-packageX')

