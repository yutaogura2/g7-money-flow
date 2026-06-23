@echo off
rem Weekly macro update (Windows Task Scheduler / manual double-click).
rem Working dir = task WorkingDirectory, or this file's folder when double-clicked.
echo [%date% %time%] update start >> update_macro.log
python fetch_macro.py >> update_macro.log 2>&1
python build.py >> update_macro.log 2>&1
git add macro_data >> update_macro.log 2>&1
git commit -m "data: weekly macro auto-update" >> update_macro.log 2>&1
echo [%date% %time%] done >> update_macro.log
