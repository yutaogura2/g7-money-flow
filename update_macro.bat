@echo off
rem Data fetch / push / public update are now handled by GitHub Actions (cloud).
rem This local task only pulls the cloud-latest and regenerates the local Excel/view.
rem (It does NOT commit or push, to avoid diverging from the CI history.)
echo [%date% %time%] local sync start >> update_macro.log
git pull --ff-only >> update_macro.log 2>&1
python build.py >> update_macro.log 2>&1
echo [%date% %time%] done >> update_macro.log
