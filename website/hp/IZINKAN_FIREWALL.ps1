# Izinkan BDM Saku menerima sinkron dari HP. Jalankan SEKALI sebagai Administrator.
#
# Yang dilakukan:
#  1. Hapus aturan "python.exe -> Block" (terbuat waktu prompt firewall dulu di-cancel).
#     Aturan Block selalu menang atas Allow, jadi selama masih ada, port apa pun ketutup.
#  2. Buka HANYA port 8765 (TCP) & 8766 (UDP) untuk Python, dan cuma dari
#     jaringan lokal yang sama -- bukan "izinkan Python seluruhnya".
#
# Profil jaringan WiFi TIDAK diubah ke Private: di WiFi bersama (kost) Public
# lebih aman karena berbagi file/penemuan perangkat tetap mati.
$ErrorActionPreference = 'Stop'
$py = (Get-Command python -ErrorAction Stop).Source

Get-NetFirewallApplicationFilter | Where-Object { $_.Program -ieq $py } | Get-NetFirewallRule |
    Where-Object { $_.Direction -eq 'Inbound' -and $_.Action -eq 'Block' } |
    ForEach-Object { Write-Host "Hapus: $($_.DisplayName) [$($_.Profile)]"; Remove-NetFirewallRule -Name $_.Name }

Get-NetFirewallRule -DisplayName 'BDM Saku *' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'BDM Saku (TCP 8765)' -Direction Inbound -Action Allow -Program $py `
    -Protocol TCP -LocalPort 8765 -RemoteAddress LocalSubnet -Profile Any | Out-Null
New-NetFirewallRule -DisplayName 'BDM Saku (UDP 8766)' -Direction Inbound -Action Allow -Program $py `
    -Protocol UDP -LocalPort 8766 -RemoteAddress LocalSubnet -Profile Any | Out-Null

Write-Host 'Selesai. Jalankan ulang KIRIM_KE_HP.bat lalu sinkron dari HP.'
Read-Host 'Enter untuk menutup'
