
::mkdir test-reports
set CI=True
@echo off
call :sub >test-report.txt
exit /b

:sub
python -m nose2 --verbose discover tests "test_*.py"
