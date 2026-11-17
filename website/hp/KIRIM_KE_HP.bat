@echo off
rem Ekspor data olahan terbaru lalu siaga mengirimnya ke BDM Saku lewat WiFi.
rem Tambahkan --tanpa-ekspor untuk langsung mengirim file ekspor terakhir.
title BDM Saku - kirim ke HP
cd /d "%~dp0..\.."
python -X utf8 -m website.kirim_hp %*
pause
